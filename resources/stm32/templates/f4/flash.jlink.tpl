device STM32F427IIH6
si SWD
speed 4000
connect
h
loadfile "${BUILD_DIR}/firmware.elf"
r
g
exit
