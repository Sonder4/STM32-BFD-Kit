scriptDir = fileparts(mfilename('fullpath'));
datasetDir = fileparts(scriptDir);
addpath(scriptDir);

[T, manifest, data] = import_bfd_dataset(datasetDir);
outDir = fullfile(datasetDir, 'matlab_out');
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

report = strings(0, 1);
report(end + 1) = "# BFD Kalman Parameter Report";
report(end + 1) = "";
report(end + 1) = "dataset: " + string(datasetDir);

columns = unique([data.sensorColumns, data.stateColumns, data.outputColumns], 'stable');
if isempty(columns)
    columns = data.valueColumns;
end
report(end + 1) = "columns: " + strjoin(string(columns), ", ");

measurementNoiseCov = [];
processNoiseCov = [];

if isempty(columns)
    report(end + 1) = "status: skipped, no numeric value columns found";
else
    X = zeros(height(T), numel(columns));
    for i = 1:numel(columns)
        X(:, i) = T.(columns{i});
    end
    valid = all(isfinite(X), 2);
    if sum(valid) > 1
        measurementNoiseCov = cov(X(valid, :));
        report(end + 1) = "measurement R: covariance estimated from selected measurement/state columns";
        report(end + 1) = "measurement_R: `" + matrix_to_text(measurementNoiseCov) + "`";
    else
        measurementNoiseCov = zeros(numel(columns));
        report(end + 1) = "measurement R: insufficient valid rows, emitted zeros";
        report(end + 1) = "measurement_R: `" + matrix_to_text(measurementNoiseCov) + "`";
    end

    if sum(valid) > 2
        dX = diff(X(valid, :));
        processNoiseCov = cov(dX);
        report(end + 1) = "process Q: covariance estimated from first differences";
        report(end + 1) = "process_Q: `" + matrix_to_text(processNoiseCov) + "`";
    else
        processNoiseCov = zeros(numel(columns));
        report(end + 1) = "process Q: insufficient valid row differences, emitted zeros";
        report(end + 1) = "process_Q: `" + matrix_to_text(processNoiseCov) + "`";
    end
end

save(fullfile(outDir, 'kalman_tuning_result.mat'), 'T', 'manifest', 'data', 'columns', 'measurementNoiseCov', 'processNoiseCov');
writelines(report, fullfile(outDir, 'kalman_tuning_report.md'));

function text = matrix_to_text(value)
if isempty(value)
    text = "[]";
else
    text = string(mat2str(value, 8));
end
end
