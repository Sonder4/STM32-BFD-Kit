scriptDir = fileparts(mfilename('fullpath'));
datasetDir = fileparts(scriptDir);
addpath(scriptDir);

[T, manifest, data] = import_bfd_dataset(datasetDir);
outDir = fullfile(datasetDir, 'matlab_out');
if ~exist(outDir, 'dir')
    mkdir(outDir);
end

products = [
    "Simulink"
    "MATLAB Coder"
    "Simulink Coder"
    "Embedded Coder"
    "Fixed-Point Designer"
    "Simulink Test"
    "MATLAB Test"
];

installed = string({ver().Name})';
availability = table(products, ismember(products, installed), 'VariableNames', {'Product', 'Installed'});

report = strings(0, 1);
report(end + 1) = "# BFD MCD Codegen Check";
report(end + 1) = "";
report(end + 1) = "dataset: " + string(datasetDir);
report(end + 1) = "samples: " + string(height(T));
report(end + 1) = "value columns: " + strjoin(string(data.valueColumns), ", ");
report(end + 1) = "";
report(end + 1) = "## Toolboxes";
for i = 1:height(availability)
    report(end + 1) = "- " + availability.Product(i) + ": " + string(availability.Installed(i));
end
report(end + 1) = "- Simulink Agentic Toolkit satk_initialize: " + string(exist('satk_initialize', 'file') == 2);
report(end + 1) = "";
report(end + 1) = "## MCU Integration Rules";
report(end + 1) = "- generated C/C++ enters USER/Modules or USER/APP wrappers, not CubeMX generated directories";
report(end + 1) = "- generated code must be wrapped by a small hand-written adapter before build";
report(end + 1) = "- fixed-point, stack, heap, and execution-time limits must be checked before hardware use";
report(end + 1) = "- J-Link HSS feedback captures should be compared against the Matlab reference run";

save(fullfile(outDir, 'mcd_codegen_check_result.mat'), 'T', 'manifest', 'data', 'availability');
writelines(report, fullfile(outDir, 'mcd_codegen_check_report.md'));
