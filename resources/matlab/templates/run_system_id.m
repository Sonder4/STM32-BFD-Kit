scriptDir = fileparts(mfilename('fullpath'));
datasetDir = fileparts(scriptDir);
addpath(scriptDir);

[T, manifest, data] = import_bfd_dataset(datasetDir);
outDir = fullfile(datasetDir, 'matlab_out');
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

report = strings(0, 1);
report(end + 1) = "# BFD System Identification Report";
report(end + 1) = "";
report(end + 1) = "dataset: " + string(datasetDir);
report(end + 1) = "samples: " + string(height(T));
report(end + 1) = "value columns: " + strjoin(string(data.valueColumns), ", ");

sys = [];
z = [];
fitInfo = struct();

if isempty(data.inputColumns) || isempty(data.outputColumns)
    report(end + 1) = "status: skipped, manifest has no input/output column classification";
else
    Ts = median(diff(data.time_s));
    if ~isfinite(Ts) || Ts <= 0
        Ts = manifest.capture.period_us / 1e6;
    end
    inputName = data.inputColumns{1};
    outputName = data.outputColumns{1};
    report(end + 1) = "input: " + string(inputName);
    report(end + 1) = "output: " + string(outputName);
    report(end + 1) = "sample_time_s: " + scalar_to_text(Ts);
    u = T.(inputName);
    y = T.(outputName);
    valid = isfinite(u) & isfinite(y);
    u = u(valid);
    y = y(valid);
    if numel(y) < 4
        report(end + 1) = "status: skipped, not enough valid samples for identification";
    elseif exist('iddata', 'file') ~= 2
        report(end + 1) = "status: skipped, System Identification Toolbox is unavailable";
    else
        z = iddata(y, u, Ts, 'InputName', inputName, 'OutputName', outputName);
        try
            sys = n4sid(z, 1);
            fitInfo.method = "n4sid_order1";
            report(end + 1) = "status: estimated model with n4sid order 1";
        catch n4sidError
            try
                sys = tfest(z, 1, 0);
                fitInfo.method = "tfest_np1_nz0";
                fitInfo.n4sid_error = string(n4sidError.message);
                report(end + 1) = "status: estimated model with tfest first order";
            catch tfestError
                fitInfo.method = "failed";
                fitInfo.n4sid_error = string(n4sidError.message);
                fitInfo.tfest_error = string(tfestError.message);
                report(end + 1) = "status: failed to estimate model";
            end
        end
    end
end

if ~isempty(sys)
    report(end + 1) = "";
    report(end + 1) = "## Identified Model";
    report(end + 1) = "method: " + string(fitInfo.method);
    try
        report(end + 1) = "dc_gain: " + scalar_to_text(dcgain(sys));
    catch
        report(end + 1) = "dc_gain: unavailable";
    end
    try
        sysSs = ss(sys);
        [A, B, C, D] = ssdata(sysSs);
        report(end + 1) = "A: `" + matrix_to_text(A) + "`";
        report(end + 1) = "B: `" + matrix_to_text(B) + "`";
        report(end + 1) = "C: `" + matrix_to_text(C) + "`";
        report(end + 1) = "D: `" + matrix_to_text(D) + "`";
    catch ssError
        report(end + 1) = "state_space: unavailable, " + string(ssError.message);
    end
end

save(fullfile(outDir, 'system_id_result.mat'), 'T', 'manifest', 'data', 'sys', 'z', 'fitInfo');
writelines(report, fullfile(outDir, 'system_id_report.md'));

function text = matrix_to_text(value)
text = string(mat2str(value, 8));
end

function text = scalar_to_text(value)
if isempty(value) || ~all(isfinite(value(:)))
    text = "unavailable";
else
    text = string(sprintf('%.9g', value(1)));
end
end
