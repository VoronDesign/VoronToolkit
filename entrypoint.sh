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


echo -e "\033[91m"
echo "           ((((           (((("
echo "        ((((((((((.    (((((((((("
echo "      (############(((############("
echo "      ((((######   *((    #####(((("
echo "      ((((((((    (((   ((((((((((("
echo "      ####(((   ###   ###((((((####"
echo "      #((((((((((    #(    (((((((#"
echo "        #######*   (((   ########"
echo "           ####(((((((((((####"
echo "              #############"
echo "                 #######"
echo "                    #"
echo -e "\033[39m"
echo " Welcome to the VoronDesign toolkit docker container!"
echo " If you encounter any issues, please report them to the VoronDesign team!"
echo ""

"$@" &
pid="${!}"
wait "${pid}"
