# Shared environment for the PEA pipeline scripts. Sourced, not executed:
#   . "$(dirname "${BASH_SOURCE[0]}")/pea_env.sh"
# PEA_ROOT  data tree (data/, processed_HF/, processed_LF/, archive/); may be a network share
# PEA_LOGS  log directory, default $PEA_ROOT/logs; set it to a local disk when PEA_ROOT is a CIFS share
# TS        this repo (the scripts, eddypro/, DataProcessingScriptsJulia/); must be on a local disk
PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
PEA_LOGS=${PEA_LOGS:-$PEA_ROOT/logs}
TS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
JL=$TS/DataProcessingScriptsJulia
PEA_INPUT_BASE=${PEA_INPUT_BASE:-$PEA_ROOT/data}
PEA_HF_OUT=${PEA_HF_OUT:-$PEA_ROOT/processed_HF}
PEA_LF_OUT=${PEA_LF_OUT:-$PEA_ROOT/processed_LF}
export PEA_ROOT PEA_LOGS PEA_INPUT_BASE PEA_HF_OUT PEA_LF_OUT
mkdir -p "$PEA_LOGS"
