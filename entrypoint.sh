#!/bin/bash

set +x
pid="0"

handle_signal() {
  echo "Signal!"
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
echo " VoronDesign docker toolkit ..."
echo ""

"$@" &
pid="${!}"
wait "${pid}"
