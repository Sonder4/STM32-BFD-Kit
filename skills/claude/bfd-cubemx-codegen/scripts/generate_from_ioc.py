#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class RunResult:
  ioc_path: Path
  cubemx_path: Path
  log_path: Path
  report_path: Path
  command_file: Path
  exit_code: int
  ioc_hash_before: str
  ioc_hash_after: str
  restored_ioc: bool
  project_markers: list[str]


def hash_file(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open('rb') as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
      digest.update(chunk)
  return digest.hexdigest()


def timestamp_now() -> str:
  return datetime.now().strftime('%Y%m%d_%H%M%S')


def find_ioc(project_root: Path) -> Path:
  matches = sorted(project_root.rglob('*.ioc'))
  if not matches:
    raise FileNotFoundError(f'no .ioc file found under {project_root}')
  if len(matches) > 1:
    listed = '\n'.join(f'  - {path}' for path in matches)
    raise RuntimeError(f'multiple .ioc files found under {project_root}:\n{listed}\nuse --ioc explicitly')
  return matches[0]


def iter_cubemx_candidates(explicit: Optional[str]) -> Iterable[Path]:
  if explicit:
    yield Path(explicit).expanduser()
  env_path = os.environ.get('STM32CUBEMX_EXE')
  if env_path:
    yield Path(env_path).expanduser()
  which_path = shutil.which('STM32CubeMX')
  if which_path:
    yield Path(which_path)
  home = Path.home()
  yield home / 'STM32CubeMX' / 'STM32CubeMX'
  yield Path('/opt/st/stm32cubemx/STM32CubeMX')


def find_cubemx(explicit: Optional[str]) -> Path:
  seen: set[Path] = set()
  for candidate in iter_cubemx_candidates(explicit):
    candidate = candidate.resolve() if candidate.exists() else candidate
    if candidate in seen:
      continue
    seen.add(candidate)
    if candidate.is_file() and os.access(candidate, os.X_OK):
      return candidate
  raise FileNotFoundError('STM32CubeMX executable not found; pass --cubemx or set STM32CUBEMX_EXE')


def ensure_in_repo(path: Path, repo_root: Path) -> Path:
  resolved = path.resolve()
  try:
    resolved.relative_to(repo_root.resolve())
  except ValueError as exc:
    raise RuntimeError(f'path must stay inside repository: {resolved}') from exc
  return resolved


def write_command_file(path: Path, ioc_path: Path) -> None:
  path.write_text(f'config load {ioc_path}\nproject generate\nexit\n', encoding='utf-8')


def collect_project_markers(project_root: Path) -> list[str]:
  markers = [
    project_root / 'Core' / 'Src' / 'main.c',
    project_root / 'Core' / 'Inc' / 'main.h',
    project_root / 'Drivers',
    project_root / 'USB_DEVICE',
    project_root / 'Middlewares',
    project_root / 'CMakeLists.txt',
  ]
  return [str(path) for path in markers if path.exists()]


def write_report(result: RunResult) -> None:
  lines = [
    '# CubeMX Codegen Report',
    '',
    f'- Time: `{datetime.now().isoformat(timespec="seconds")}`',
    f'- IOC: `{result.ioc_path}`',
    f'- CubeMX: `{result.cubemx_path}`',
    f'- Log: `{result.log_path}`',
    f'- Command file: `{result.command_file}`',
    f'- Exit code: `{result.exit_code}`',
    f'- IOC hash before: `{result.ioc_hash_before}`',
    f'- IOC hash after: `{result.ioc_hash_after}`',
    f'- IOC restored: `{result.restored_ioc}`',
    '',
    '## Project Markers',
    '',
  ]
  if result.project_markers:
    lines.extend(f'- `{marker}`' for marker in result.project_markers)
  else:
    lines.append('- No common generated markers detected.')
  result.report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description='Generate STM32CubeMX-managed code from an existing .ioc without changing configuration.')
  parser.add_argument('--ioc', help='Explicit .ioc file path.')
  parser.add_argument('--project-root', default='.', help='Project root used to auto-discover a single .ioc file.')
  parser.add_argument('--cubemx', help='Explicit STM32CubeMX executable path.')
  parser.add_argument('--log-dir', default='logs/skills', help='Repository-local directory for logs and reports.')
  parser.add_argument('--report', help='Explicit markdown report path.')
  parser.add_argument('--keep-temp', action='store_true', help='Keep the temporary CubeMX command file.')
  return parser.parse_args()


def main() -> int:
  args = parse_args()
  repo_root = Path.cwd().resolve()
  log_dir = ensure_in_repo((repo_root / args.log_dir).resolve(), repo_root)
  log_dir.mkdir(parents=True, exist_ok=True)

  if args.ioc:
    ioc_path = Path(args.ioc).expanduser().resolve()
  else:
    ioc_path = find_ioc(Path(args.project_root).expanduser().resolve())

  if not ioc_path.is_file():
    raise FileNotFoundError(f'.ioc file not found: {ioc_path}')

  cubemx_path = find_cubemx(args.cubemx)
  stamp = timestamp_now()
  log_path = log_dir / f'cubemx_codegen_{stamp}.log'
  report_path = Path(args.report).expanduser().resolve() if args.report else log_dir / f'cubemx_codegen_{stamp}.md'
  report_path = ensure_in_repo(report_path, repo_root)
  command_file = log_dir / f'cubemx_codegen_{stamp}.mxs'

  original_bytes = ioc_path.read_bytes()
  ioc_hash_before = hash_file(ioc_path)
  write_command_file(command_file, ioc_path)

  with log_path.open('w', encoding='utf-8') as log_handle:
    process = subprocess.run(
      [str(cubemx_path), '-q', str(command_file)],
      stdout=log_handle,
      stderr=subprocess.STDOUT,
      check=False,
      cwd=str(ioc_path.parent),
    )

  restored_ioc = False
  ioc_hash_after = hash_file(ioc_path)
  if ioc_hash_after != ioc_hash_before:
    ioc_path.write_bytes(original_bytes)
    restored_ioc = True
    ioc_hash_after = hash_file(ioc_path)
    exit_code = process.returncode if process.returncode != 0 else 2
  else:
    exit_code = process.returncode

  result = RunResult(
    ioc_path=ioc_path,
    cubemx_path=cubemx_path,
    log_path=log_path,
    report_path=report_path,
    command_file=command_file,
    exit_code=exit_code,
    ioc_hash_before=ioc_hash_before,
    ioc_hash_after=ioc_hash_after,
    restored_ioc=restored_ioc,
    project_markers=collect_project_markers(ioc_path.parent),
  )
  write_report(result)

  if not args.keep_temp and command_file.exists():
    command_file.unlink()

  if restored_ioc:
    print(f'[ERROR] .ioc changed during generation and was restored: {ioc_path}', file=sys.stderr)
  if exit_code != 0:
    print(f'[ERROR] CubeMX generation failed, see log: {log_path}', file=sys.stderr)
  else:
    print(f'[OK] CubeMX generation completed: {log_path}')
    print(f'[OK] Report written: {report_path}')
  return exit_code


if __name__ == '__main__':
  sys.exit(main())
