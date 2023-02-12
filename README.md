# zig-download

Tool for downloading precompiled zig tarballs from https://ziglang.org/download/ .
This is basically the same thing as [zigup](https://github.com/marler8997/zigup), but I wrote this one as an exercise.

Usage:

```
zig run zig-download.zig
```

Then put the following on your PATH: `~/zig-downloads/active`

#### Python version???

There seems to be a bug somewhere in the Zig https -> xz -> untar pipeline that causes the program to hang at 100% CPU.
I wrote a Python version for now.
