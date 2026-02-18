CC      = gcc
CFLAGS  = -O2 -Wall -Wextra
# MiniFB on Linux requires X11 and GL.
# Install MiniFB: https://github.com/nicowillis/minifb (cmake --install)
LIBS    = -lminifb -lzmq -lX11 -lGL -lm

TARGET  = main
SRCS    = main.c packet.c

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SRCS) packet.h
	$(CC) $(CFLAGS) -o $@ $(SRCS) $(LIBS)

clean:
	rm -f $(TARGET)

run: $(TARGET)
	./$(TARGET)
