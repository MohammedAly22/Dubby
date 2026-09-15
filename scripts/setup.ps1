# Dubby 🐨 setup (Windows PowerShell)
#   .\scripts\setup.ps1                core env only
#   .\scripts\setup.ps1 -Qwen          + Qwen3-ASR / QwenCleo env
#   .\scripts\setup.ps1 -Nemo          + NVIDIA Parakeet env
#   .\scripts\setup.ps1 -Cpu           CPU-only PyTorch wheels
param([switch]$Qwen, [switch]$Nemo, [switch]$Cpu)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Say($msg) { Write-Host "`n🐨 $msg" -ForegroundColor White }

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) { throw "conda not found — install Miniconda and open an Anaconda PowerShell prompt." }

function New-DubbyEnv($yml, $name) {
    if ($Cpu) {
        $tmp = ".$yml.cpu.yml"
        (Get-Content $yml) -replace 'whl/cu128', 'whl/cpu' | Set-Content -Encoding utf8 $tmp
        $yml = $tmp
    }
    $exists = conda env list | Select-String -Pattern "^$name\s"
    if ($exists) { Say "Updating env $name"; conda env update -n $name -f $yml --prune }
    else { Say "Creating env $name"; conda env create -f $yml }
}

New-DubbyEnv "environment.yml" "dubby"
if ($Qwen) { New-DubbyEnv "environment-qwen.yml" "dubby-qwen"; conda run -n dubby-qwen pip install qwencleo-asr --no-deps }
if ($Nemo) { New-DubbyEnv "environment-nemo.yml" "dubby-nemo" }

Say "Building the web UI"
conda run -n dubby --no-capture-output dubby build-ui

Say "Checking engines"
conda run -n dubby --no-capture-output dubby doctor

Say "Done! Start the studio with:  conda activate dubby; dubby serve"
