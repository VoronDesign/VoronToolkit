#!/bin/bash

set +x
pid="0"

handle_signal() {
  echo "Signal received!"
  if [ "x${pid}" != "x0" ]; then
    kill -SIGTERM "${pid}"
    wait "${pid}"
  fi
  exit 0
}

trap 'handle_signal' SIGINT SIGTERM SIGHUP SIGUSR1 SIGUSR2

print_help() {
  echo "Print help called!"
}

echo -e "\033[1;91m"
echo -e "\033[1;91m           ((((           (((("
echo -e "\033[1;91m        ((((((((((.    (((((((((("
echo -e "\033[1;91m      (############(((############("
echo -e "\033[1;91m      ((((######   *((    #####(((("
echo -e "\033[1;91m      ((((((#(    (((   ((((#(((((("
echo -e "\033[1;91m      #####((   ###   ####((((#####"
echo -e "\033[1;91m      #((((((((((    #(    (((((((#"
echo -e "\033[1;91m        #######*   (((   ########"
echo -e "\033[1;91m           ####(((((((((((####"
echo -e "\033[1;91m              #############"
echo -e "\033[1;91m                 #######"
echo -e "\033[1;91m                    #"
echo -e "\033[39m"
echo " Welcome to the VoronDesign Toolkit docker container!"
echo " If you encounter any issues, please report them to the VoronDesign team!"
echo ""

"$@" &
pid="${!}"
wait "${pid}"
