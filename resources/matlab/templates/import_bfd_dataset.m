function [T, manifest, data] = import_bfd_dataset(datasetDir)
if nargin < 1 || isempty(datasetDir)
    scriptDir = fileparts(mfilename('fullpath'));
    datasetDir = fileparts(scriptDir);
end

manifestPath = fullfile(datasetDir, 'manifest.json');
if ~isfile(manifestPath)
    error('BFD:MissingManifest', 'manifest.json not found: %s', manifestPath);
end

manifest = jsondecode(fileread(manifestPath));
csvPath = fullfile(datasetDir, manifest.capture.csv);
if ~isfile(csvPath)
    csvPath = fullfile(datasetDir, 'capture.csv');
end
if ~isfile(csvPath)
    error('BFD:MissingCapture', 'capture CSV not found in dataset: %s', datasetDir);
end

opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
T = readtable(csvPath, opts);
names = T.Properties.VariableNames;

if any(strcmp(names, 'time_us'))
    time_s = T.('time_us') / 1e6;
elseif any(strcmp(names, 'time_s'))
    time_s = T.('time_s');
else
    time_s = (0:height(T)-1)';
end

valueColumns = names(endsWith(names, '__value'));
if isempty(valueColumns)
    valueColumns = {};
    for i = 1:numel(names)
        name = names{i};
        if any(strcmp(name, {'sample_index', 'time_us', 'time_s'})) || contains(name, 'raw_hex')
            continue;
        end
        if isnumeric(T.(name))
            valueColumns{end + 1} = name; %#ok<AGROW>
        end
    end
end

classification = struct();
if isfield(manifest, 'classification')
    classification = manifest.classification;
end

data = struct();
data.datasetDir = datasetDir;
data.csvPath = csvPath;
data.time_s = time_s;
data.valueColumns = valueColumns;
data.inputColumns = existing_columns(valueColumns, field_or_empty(classification, 'input_columns'));
data.outputColumns = existing_columns(valueColumns, field_or_empty(classification, 'output_columns'));
data.stateColumns = existing_columns(valueColumns, field_or_empty(classification, 'state_columns'));
data.sensorColumns = existing_columns(valueColumns, field_or_empty(classification, 'sensor_columns'));
data.motorColumns = existing_columns(valueColumns, field_or_empty(classification, 'motor_columns'));
end

function values = field_or_empty(payload, fieldName)
if isstruct(payload) && isfield(payload, fieldName)
    values = normalize_strings(payload.(fieldName));
else
    values = {};
end
end

function values = normalize_strings(raw)
if isempty(raw)
    values = {};
elseif iscell(raw)
    values = raw(:)';
elseif isstring(raw)
    values = cellstr(raw(:))';
elseif ischar(raw)
    values = {raw};
else
    values = {};
end
end

function values = existing_columns(allColumns, requested)
values = {};
for i = 1:numel(requested)
    if any(strcmp(allColumns, requested{i}))
        values{end + 1} = requested{i}; %#ok<AGROW>
    end
end
end
