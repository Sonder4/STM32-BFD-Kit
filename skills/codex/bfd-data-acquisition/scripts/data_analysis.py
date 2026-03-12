#!/usr/bin/env python3
"""
STM32 Data Analysis Script
分析采集的数据，支持统计分析、波形绘制、FFT频谱分析

Usage:
    python data_analysis.py --input data.csv --stats
    python data_analysis.py --input data.csv --plot waveform.png
    python data_analysis.py --input data.csv --fft --output spectrum.png
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import struct
import math

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: numpy not available, some features disabled")

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, plotting disabled")


class DataAnalyzer:
    def __init__(self, data: List[Dict], metadata: Dict = None):
        self.data = data
        self.metadata = metadata or {}
        self.timestamps = []
        self.values = {}
        self._parse_data()

    def _parse_data(self):
        if not self.data:
            return
        
        first_sample = self.data[0]
        
        if 'value' in first_sample:
            self.timestamps = [s['timestamp'] for s in self.data]
            self.values['value'] = [s['value'] for s in self.data]
        elif 'data' in first_sample:
            self.timestamps = [s['timestamp'] for s in self.data]
            self.values['raw'] = [s['data'] for s in self.data]
        else:
            self.timestamps = [s.get('timestamp', i) for i, s in enumerate(self.data)]
            for key in first_sample.keys():
                if key != 'timestamp':
                    self.values[key] = [s.get(key, 0) for s in self.data]

    def load_csv(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r', newline='') as f:
                reader = csv.DictReader(f)
                self.data = list(reader)
                self._parse_data()
            return True
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return False

    def load_json(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r') as f:
                content = json.load(f)
                if isinstance(content, dict):
                    self.metadata = content.get('metadata', {})
                    self.data = content.get('data', [])
                else:
                    self.data = content
                self._parse_data()
            return True
        except Exception as e:
            print(f"Error loading JSON: {e}")
            return False

    def get_statistics(self, channel: str = None) -> Dict[str, float]:
        if channel is None:
            channel = list(self.values.keys())[0] if self.values else 'value'
        
        if channel not in self.values or not self.values[channel]:
            return {}
        
        values = self.values[channel]
        
        if NUMPY_AVAILABLE:
            arr = np.array(values, dtype=float)
            stats = {
                'count': len(arr),
                'min': float(np.min(arr)),
                'max': float(np.max(arr)),
                'mean': float(np.mean(arr)),
                'std': float(np.std(arr)),
                'variance': float(np.var(arr)),
                'median': float(np.median(arr)),
            }
            
            if len(arr) > 1:
                percentiles = [25, 50, 75, 90, 95, 99]
                for p in percentiles:
                    stats[f'p{p}'] = float(np.percentile(arr, p))
            
            return stats
        else:
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            mean_val = sum(values) / n
            
            variance = sum((x - mean_val) ** 2 for x in values) / n
            
            return {
                'count': n,
                'min': sorted_vals[0],
                'max': sorted_vals[-1],
                'mean': mean_val,
                'std': math.sqrt(variance),
                'variance': variance,
                'median': sorted_vals[n // 2] if n % 2 else (sorted_vals[n//2-1] + sorted_vals[n//2]) / 2,
            }

    def compute_fft(self, channel: str = None, sample_rate: float = None) -> Tuple[List[float], List[float]]:
        if not NUMPY_AVAILABLE:
            print("Error: numpy required for FFT analysis")
            return [], []
        
        if channel is None:
            channel = list(self.values.keys())[0] if self.values else 'value'
        
        if channel not in self.values:
            return [], []
        
        values = np.array(self.values[channel], dtype=float)
        
        if sample_rate is None:
            if len(self.timestamps) > 1:
                dt = self.timestamps[1] - self.timestamps[0]
                sample_rate = 1.0 / dt if dt > 0 else 1000.0
            else:
                sample_rate = 1000.0
        
        n = len(values)
        fft_result = np.fft.fft(values)
        freqs = np.fft.fftfreq(n, 1.0 / sample_rate)
        
        positive_mask = freqs >= 0
        freqs = freqs[positive_mask]
        magnitudes = np.abs(fft_result[positive_mask]) * 2 / n
        
        return freqs.tolist(), magnitudes.tolist()

    def plot_waveform(self, output_file: str, channels: List[str] = None, 
                      zoom: Tuple[float, float] = None, title: str = None):
        if not MATPLOTLIB_AVAILABLE:
            print("Error: matplotlib required for plotting")
            return False
        
        if channels is None:
            channels = list(self.values.keys())[:4]
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        for channel in channels:
            if channel in self.values:
                times = self.timestamps
                values = self.values[channel]
                
                if zoom:
                    start_idx = 0
                    end_idx = len(times)
                    for i, t in enumerate(times):
                        if t >= zoom[0] and start_idx == 0:
                            start_idx = i
                        if t >= zoom[1]:
                            end_idx = i
                            break
                    times = times[start_idx:end_idx]
                    values = values[start_idx:end_idx]
                
                ax.plot(times, values, label=channel, linewidth=0.8)
        
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Value')
        ax.set_title(title or 'Data Waveform')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()
        
        print(f"Waveform saved to: {output_file}")
        return True

    def plot_spectrum(self, output_file: str, channel: str = None, 
                      sample_rate: float = None, title: str = None):
        if not MATPLOTLIB_AVAILABLE or not NUMPY_AVAILABLE:
            print("Error: matplotlib and numpy required for spectrum plotting")
            return False
        
        freqs, magnitudes = self.compute_fft(channel, sample_rate)
        
        if not freqs:
            return False
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        ax.plot(freqs, magnitudes, linewidth=0.8)
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Magnitude')
        ax.set_title(title or 'Frequency Spectrum')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, max(freqs) / 2 if freqs else 1000)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()
        
        print(f"Spectrum saved to: {output_file}")
        return True

    def plot_histogram(self, output_file: str, channel: str = None, 
                       bins: int = 50, title: str = None):
        if not MATPLOTLIB_AVAILABLE:
            print("Error: matplotlib required for plotting")
            return False
        
        if channel is None:
            channel = list(self.values.keys())[0] if self.values else 'value'
        
        if channel not in self.values:
            return False
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        ax.hist(self.values[channel], bins=bins, edgecolor='black', alpha=0.7)
        ax.set_xlabel('Value')
        ax.set_ylabel('Count')
        ax.set_title(title or f'Histogram - {channel}')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()
        
        print(f"Histogram saved to: {output_file}")
        return True

    def export_csv(self, output_file: str):
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            header = ['timestamp'] + list(self.values.keys())
            writer.writerow(header)
            
            for i, ts in enumerate(self.timestamps):
                row = [ts]
                for channel in self.values.keys():
                    if i < len(self.values[channel]):
                        row.append(self.values[channel][i])
                    else:
                        row.append('')
                writer.writerow(row)
        
        print(f"Data exported to CSV: {output_file}")

    def export_json(self, output_file: str):
        output = {
            'metadata': self.metadata,
            'statistics': {},
            'data': self.data
        }
        
        for channel in self.values.keys():
            output['statistics'][channel] = self.get_statistics(channel)
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"Data exported to JSON: {output_file}")

    def print_summary(self):
        print("\n" + "=" * 60)
        print("Data Analysis Summary")
        print("=" * 60)
        
        if self.metadata:
            print("\nMetadata:")
            for key, value in self.metadata.items():
                print(f"  {key}: {value}")
        
        print(f"\nTotal samples: {len(self.data)}")
        print(f"Channels: {list(self.values.keys())}")
        
        if self.timestamps:
            duration = self.timestamps[-1] - self.timestamps[0]
            print(f"Duration: {duration:.3f} seconds")
            if len(self.timestamps) > 1:
                avg_rate = len(self.timestamps) / duration if duration > 0 else 0
                print(f"Average sample rate: {avg_rate:.1f} Hz")
        
        print("\nStatistics per channel:")
        for channel in self.values.keys():
            stats = self.get_statistics(channel)
            print(f"\n  [{channel}]")
            for key, value in stats.items():
                if isinstance(value, float):
                    print(f"    {key}: {value:.4f}")
                else:
                    print(f"    {key}: {value}")
        
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='STM32 Data Analysis Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input data.csv --stats
  %(prog)s --input data.csv --plot waveform.png
  %(prog)s --input data.csv --fft --output spectrum.png
  %(prog)s --input data.csv --convert json --output data.json
        """
    )
    
    parser.add_argument('--input', '-i', required=True,
                       help='Input data file (CSV or JSON)')
    parser.add_argument('--output', '-o',
                       help='Output file path')
    parser.add_argument('--stats', action='store_true',
                       help='Print statistical summary')
    parser.add_argument('--plot',
                       help='Generate waveform plot (specify output file)')
    parser.add_argument('--fft', action='store_true',
                       help='Perform FFT analysis')
    parser.add_argument('--histogram',
                       help='Generate histogram (specify output file)')
    parser.add_argument('--channels',
                       help='Comma-separated list of channels to plot')
    parser.add_argument('--sample-rate', type=float,
                       help='Sample rate for FFT (Hz)')
    parser.add_argument('--convert', choices=['csv', 'json'],
                       help='Convert data format')
    parser.add_argument('--zoom',
                       help='Time range for plot zoom (start,end)')
    parser.add_argument('--bins', type=int, default=50,
                       help='Number of histogram bins')
    
    args = parser.parse_args()
    
    analyzer = DataAnalyzer([])
    
    if args.input.endswith('.json'):
        analyzer.load_json(args.input)
    else:
        analyzer.load_csv(args.input)
    
    if not analyzer.data:
        print("Error: No data loaded")
        return
    
    if args.stats or not any([args.plot, args.fft, args.histogram, args.convert]):
        analyzer.print_summary()
    
    if args.plot:
        channels = None
        if args.channels:
            channels = [c.strip() for c in args.channels.split(',')]
        
        zoom = None
        if args.zoom:
            parts = args.zoom.split(',')
            if len(parts) == 2:
                zoom = (float(parts[0]), float(parts[1]))
        
        analyzer.plot_waveform(args.plot, channels, zoom)
    
    if args.fft:
        output = args.output or 'spectrum.png'
        analyzer.plot_spectrum(output, sample_rate=args.sample_rate)
    
    if args.histogram:
        analyzer.plot_histogram(args.histogram, bins=args.bins)
    
    if args.convert:
        output = args.output
        if not output:
            base = os.path.splitext(args.input)[0]
            output = f"{base}.{args.convert}"
        
        if args.convert == 'csv':
            analyzer.export_csv(output)
        else:
            analyzer.export_json(output)


if __name__ == '__main__':
    main()
