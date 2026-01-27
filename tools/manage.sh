# Colors for terminal

RST='\033[0m'             # Text Reset

# Regular Colors
Black='\033[0;30m'        # Black
Red='\033[0;31m'          # Red
Green='\033[0;32m'        # Green
Yellow='\033[0;33m'       # Yellow
Blue='\033[0;34m'         # Blue
Purple='\033[0;35m'       # Purple
Cyan='\033[0;36m'         # Cyan
White='\033[0;37m'        # White

# Bold
BBlack='\033[1;30m'       # Black
BRed='\033[1;31m'         # Red
BGreen='\033[1;32m'       # Green
BYellow='\033[1;33m'      # Yellow
BBlue='\033[1;34m'        # Blue
BPurple='\033[1;35m'      # Purple
BCyan='\033[1;36m'        # Cyan
BWhite='\033[1;37m'       # White

# Bold High Intensity
BIBlack='\033[1;90m'      # Black
BIRed='\033[1;91m'        # Red
BIGreen='\033[1;92m'      # Green
BIYellow='\033[1;93m'     # Yellow
BIBlue='\033[1;94m'       # Blue
BIPurple='\033[1;95m'     # Purple
BICyan='\033[1;96m'       # Cyan
BIWhite='\033[1;97m'      # White


##############################################################################
# Detect required version of python
# Globals:
#   colors
#   PYTHON
# Arguments:
#   None
# Returns:
#   None
###############################################################################
detect_python () {
  echo -e "${BIGreen}>>>${RST} Using python \c"
  command -v python >/dev/null 2>&1 || { echo -e "${BIRed}- NOT FOUND${RST} ${BIYellow}You need Python 3.9 installed to continue.${RST}"; return 1; }
  local version_command="import sys;print('{0}.{1}'.format(sys.version_info[0], sys.version_info[1]))"
  local python_version="$(python <<< ${version_command})"
  oIFS="$IFS"
  IFS=.
  set -- $python_version
  IFS="$oIFS"
  if [ "$1" -ge "3" ] && [ "$2" -ge "9" ] ; then
    if [ "$2" -gt "9" ] ; then
      echo -e "${BIWhite}[${RST} ${BIRed}$1.$2 ${BIWhite}]${RST} - ${BIRed}FAILED${RST} ${BIYellow}Version is new and unsupported, use${RST} ${BIPurple}3.9.x${RST}"; return 1;
    else
      echo -e "${BIWhite}[${RST} ${BIGreen}$1.$2${RST} ${BIWhite}]${RST}"
    fi
  else
    command -v python >/dev/null 2>&1 || { echo -e "${BIRed}$1.$2$ - ${BIRed}FAILED${RST} ${BIYellow}Version is old and unsupported${RST}"; return 1; }
  fi
}

##############################################################################
# Install UV
# Arguments:
#   None
# Returns:
#   None
###############################################################################
install_uv () {
  command -v uv >/dev/null 2>&1 || {
    curl -LsSf https://astral.sh/uv/install.sh | sh
  }
}

##############################################################################
# Return absolute path
# Globals:
#   None
# Arguments:
#   Path to resolve
# Returns:
#   None
###############################################################################
realpath () {
  echo $(cd $(dirname "$1"); pwd)/$(basename "$1")
}

##############################################################################
# Create Virtual Environment
# Arguments:
#   Path to resolve
# Returns:
#   None
###############################################################################
create_env () {
  # Directories
  pushd "$repo_root" > /dev/null || return > /dev/null

  uv venv --allow-existing && uv sync --all-extras || { echo -e "${BIRed}!!!${RST} Venv installation failed"; return 1; }
  if [ $? -ne 0 ] ; then
    echo -e "${BIRed}!!!${RST} Virtual environment creation failed."
    return 1
  fi

  echo -e "${BIGreen}>>>${RST} Cleaning cache files ..."
  clean_pyc

  if [ -d "$repo_root/.git" ]; then
    echo -e "${BIGreen}>>>${RST} Installing pre-commit hooks ..."
    uv run pre-commit install
  fi
}

print_art() {
  echo -e "${BGreen}"
  cat <<-EOF

                    ▄██▄
         ▄███▄ ▀██▄ ▀██▀ ▄██▀ ▄██▀▀▀██▄    ▀███▄      █▄
        ▄▄ ▀██▄  ▀██▄  ▄██▀ ██▀      ▀██▄  ▄  ▀██▄    ███
       ▄██▀  ██▄   ▀ ▄▄ ▀  ██         ▄██  ███  ▀██▄  ███
      ▄██▀    ▀██▄   ██    ▀██▄      ▄██▀  ███    ▀██ ▀█▀
     ▄██▀      ▀██▄  ▀█      ▀██▄▄▄▄██▀    █▀      ▀██▄

     ·  · - =[ by YNPUT ]:[ http://ayon.ynput.io ]= - ·  ·

EOF
  echo -e "${RST}"
}

default_help() {
  print_art
  echo -e "${BWhite}AYON Addon management script${RST}"
  echo ""
  echo -e "Usage: ${BWhite}./manage.sh${RST} ${BICyan}[command]${RST}"
  echo ""
  echo -e "${BWhite}Commands:${RST}"
  echo -e "  ${BWhite}create-env${RST}      ${BCyan}Install uv and update venv by lock file${RST}"
  echo -e "  ${BWhite}ruff-check${RST}      ${BCyan}Run Ruff check for the repository${RST}"
  echo -e "  ${BWhite}ruff-fix${RST}        ${BCyan}Run Ruff fix for the repository${RST}"
  echo -e "  ${BWhite}codespell${RST}       ${BCyan}Run codespell check for the repository${RST}"
  echo -e "  ${BWhite}run${RST}             ${BCyan}Run a uv command in the repository environment${RST}"
  echo -e "  ${BWhite}run-tests${RST}       ${BCyan}Run ayon-core tests${RST}"
  echo ""
}

run_ruff () {
  echo -e "${BIGreen}>>>${RST} Running Ruff check ..."
  "uv" run ruff check
}

run_ruff_check () {
  echo -e "${BIGreen}>>>${RST} Running Ruff fix ..."
  uv run ruff check --fix
}

run_codespell () {
  echo -e "${BIGreen}>>>${RST} Running codespell check ..."
  uv run codespell
}

run_command () {
  echo -e "${BIGreen}>>>${RST} Running ..."
  shift;  # will remove first arg ("run") from the "$@"
  uv run "$@"
}

run_tests () {
  echo -e "${BIGreen}>>>${RST} Running tests..."
  shift;  # will remove first arg ("run-tests") from the "$@"
  uv run pytest ./tests -m "not server"
}

main () {
  detect_python || return 1
  install_uv || return 1

  # Directories
  repo_root=$(realpath $(dirname $(dirname "${BASH_SOURCE[0]}")))

  pushd "$repo_root" > /dev/null || return > /dev/null

  # Use first argument, lower and keep only characters
  function_name="$(echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z]*//g')"

  case $function_name in
    "createenv")
      create_env || return_code=$?
      exit $return_code
      ;;
    "ruffcheck")
      run_ruff || return_code=$?
      exit $return_code
      ;;
    "rufffix")
      run_ruff_check || return_code=$?
      exit $return_code
      ;;
    "codespell")
      run_codespell || return_code=$?
      exit $return_code
      ;;
    "run")
      run_command "$@" || return_code=$?
      exit $return_code
      ;;
    "runtests")
      run_tests "$@" || return_code=$?
      exit $return_code
      ;;
  esac

  if [ "$function_name" != "" ]; then
    echo -e "${BIRed}!!!${RST} Unknown function name: $function_name"
  fi

  default_help
  exit $return_code
}

return_code=0
main "$@" || return_code=$?
exit $return_code
