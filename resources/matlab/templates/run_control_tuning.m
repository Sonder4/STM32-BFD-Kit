scriptDir = fileparts(mfilename('fullpath'));
datasetDir = fileparts(scriptDir);
addpath(scriptDir);

[T, manifest, data] = import_bfd_dataset(datasetDir);
outDir = fullfile(datasetDir, 'matlab_out');
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

report = strings(0, 1);
report(end + 1) = "# BFD Control Tuning Report";
report(end + 1) = "";
report(end + 1) = "dataset: " + string(datasetDir);

sys = [];
pidController = [];
pidInfo = [];
lqrGain = [];
mpcController = [];

systemIdPath = fullfile(outDir, 'system_id_result.mat');
if isfile(systemIdPath)
    loaded = load(systemIdPath);
    if isfield(loaded, 'sys')
        sys = loaded.sys;
    end
end

if isempty(sys)
    report(end + 1) = "status: skipped, no identified model found; run system-id first";
else
    try
        [pidController, pidInfo] = pidtune(sys, 'PID');
        report(end + 1) = "pid: pidtune generated a PID candidate";
        report(end + 1) = "pid.Kp: " + scalar_to_text(pidController.Kp);
        report(end + 1) = "pid.Ki: " + scalar_to_text(pidController.Ki);
        report(end + 1) = "pid.Kd: " + scalar_to_text(pidController.Kd);
        report(end + 1) = "pid.Tf: " + scalar_to_text(pidController.Tf);
        if isstruct(pidInfo) && isfield(pidInfo, 'CrossoverFrequency')
            report(end + 1) = "pid.crossover_frequency: " + scalar_to_text(pidInfo.CrossoverFrequency);
        end
        if isstruct(pidInfo) && isfield(pidInfo, 'PhaseMargin')
            report(end + 1) = "pid.phase_margin_deg: " + scalar_to_text(pidInfo.PhaseMargin);
        end
    catch pidError
        report(end + 1) = "pid: skipped, " + string(pidError.message);
    end

    try
        sysSs = ss(sys);
        [A, B, ~, ~] = ssdata(sysSs);
        Q = eye(size(A, 1));
        R = eye(size(B, 2));
        lqrGain = lqr(A, B, Q, R);
        report(end + 1) = "lqr: generated baseline Q=I, R=I gain";
        report(end + 1) = "lqr.K: `" + matrix_to_text(lqrGain) + "`";
        report(end + 1) = "lqr.Q: `" + matrix_to_text(Q) + "`";
        report(end + 1) = "lqr.R: `" + matrix_to_text(R) + "`";
    catch lqrError
        report(end + 1) = "lqr: skipped, " + string(lqrError.message);
    end

    try
        Ts = median(diff(data.time_s));
        if ~isfinite(Ts) || Ts <= 0
            Ts = manifest.capture.period_us / 1e6;
        end
        mpcController = mpc(sys, Ts);
        report(end + 1) = "mpc: generated baseline MPC object";
        report(end + 1) = "mpc.sample_time_s: " + scalar_to_text(Ts);
        report(end + 1) = "mpc.prediction_horizon: " + scalar_to_text(mpcController.PredictionHorizon);
        report(end + 1) = "mpc.control_horizon: " + scalar_to_text(mpcController.ControlHorizon);
        report(end + 1) = "mpc.weights.MV: `" + matrix_to_text(mpcController.Weights.MV) + "`";
        report(end + 1) = "mpc.weights.MVRate: `" + matrix_to_text(mpcController.Weights.MVRate) + "`";
        report(end + 1) = "mpc.weights.OV: `" + matrix_to_text(mpcController.Weights.OV) + "`";
    catch mpcError
        report(end + 1) = "mpc: skipped, " + string(mpcError.message);
    end
end

save(fullfile(outDir, 'control_tuning_result.mat'), 'T', 'manifest', 'data', 'sys', 'pidController', 'pidInfo', 'lqrGain', 'mpcController');
writelines(report, fullfile(outDir, 'control_tuning_report.md'));

function text = matrix_to_text(value)
if isempty(value)
    text = "[]";
else
    text = string(mat2str(value, 8));
end
end

function text = scalar_to_text(value)
if isempty(value) || ~all(isfinite(value(:)))
    text = "unavailable";
else
    text = string(sprintf('%.9g', value(1)));
end
end
