device STM32H723VG
si SWD
speed 4000
connect
h
loadfile "${BUILD_DIR}/firmware.elf"
r
g
exit
