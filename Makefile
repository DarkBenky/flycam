CC      = gcc
CFLAGS  = -O2 -Wall -Wextra
# MiniFB on Linux requires X11 and GL.
# Install MiniFB: https://github.com/nicowillis/minifb (cmake --install)
LIBS    = -lminifb -lzmq -llz4 -lX11 -lGL -lm

TARGET  = main
SRCS    = main.c lib/packet.c

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SRCS) lib/packet.h
	$(CC) $(CFLAGS) -o $@ $(SRCS) $(LIBS)

clean:
	rm -f $(TARGET)

run: $(TARGET)
	export $$(grep -v '^#' .env | xargs) && ./$(TARGET)
