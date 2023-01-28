const std = @import("std");

var gpa: std.mem.Allocator = undefined;
var http_client: std.http.Client = undefined;

pub fn main() !void {
    var arena_allocator = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena_allocator.deinit();
    gpa = arena_allocator.allocator();

    http_client = .{ .allocator = gpa };
    defer http_client.deinit();

    // Determine latest version.
    const download_page = try downloadEntireUrl("https://ziglang.org/download/");
    defer gpa.free(download_page);
    const url_start = std.mem.indexOf(u8, download_page, "https://ziglang.org/builds/zig-linux-x86_64-").?;
    const url_end = std.mem.indexOfAnyPos(u8, download_page, url_start, "'\"<> ").?;
    const latest_download_url = download_page[url_start..url_end];
    const latest_tar_name = latest_download_url[std.mem.lastIndexOfScalar(u8, latest_download_url, '/').? + 1..];
    std.debug.assert(std.mem.endsWith(u8, latest_tar_name, ".tar.xz"));
    const latest_name = latest_tar_name[0 .. latest_tar_name.len - ".tar.xz".len];

    // Check what we have.
    var downloads = try openDownloadsDir();
    defer downloads.close();

    if (!isDirectory(downloads, latest_name)) {
        // Download latest version.
        std.log.info("Downloading: {s}", .{latest_name});
        downloads.makeDir(".tmp") catch |err| switch (err) {
            error.PathAlreadyExists => {
                try downloads.deleteTree(".tmp");
                try downloads.makeDir(".tmp");
            },
            else => return err,
        };
        const extract_dir = try downloads.openDir(".tmp", .{});
        var req = try http_client.request(try std.Uri.parse(latest_download_url), .{}, .{});
        defer req.deinit();
        // Use a buffered reader to work around a bug in the tls implementation.
        var br = std.io.bufferedReaderSize(std.crypto.tls.max_ciphertext_record_len, req.reader());
        // Download and extract at the same time.
        var xz = try std.compress.xz.decompress(gpa, br.reader());
        defer xz.deinit();
        try std.tar.pipeToFileSystem(extract_dir, xz.reader(), .{});

        var buffer: [std.fs.MAX_PATH_BYTES]u8 = undefined;
        const sub_path = try std.fmt.bufPrint(buffer[0..], ".tmp/{s}", .{latest_name});
        try downloads.rename(sub_path, latest_name);
        try downloads.deleteTree(".tmp");
    }

    // Check active symlink.
    var buffer: [std.fs.MAX_PATH_BYTES]u8 = undefined;
    const active_link = downloads.readLink("active", buffer[0..]) catch |err| switch (err) {
        error.FileNotFound => "",
        else => return err,
    };
    if (!std.mem.eql(u8, latest_name, active_link)) {
        // Active latest version.
        std.log.info("Activating: {s}", .{latest_name});
        try downloads.symLink(".tmp", latest_name, .{});
        try downloads.rename(".tmp", "active");
    } else {
        std.log.info("Up to date. Version: {s}", .{latest_name});
    }
}

fn isDirectory(parent: std.fs.Dir, sub_path: []const u8) bool {
    const stat = parent.statFile(sub_path) catch return false;
    return stat.kind == .Directory;
}

fn downloadEntireUrl(url: []const u8) ![]u8 {
    const uri = try std.Uri.parse(url);
    var req = try http_client.request(uri, .{}, .{});
    defer req.deinit();
    // Use a buffered reader to work around a bug in the tls implementation.
    var br = std.io.bufferedReaderSize(std.crypto.tls.max_ciphertext_record_len, req.reader());
    return try br.reader().readAllAlloc(gpa, 10_000_000);
}

fn openDownloadsDir() !std.fs.Dir {
    var home_dir = try openHomeDir();
    defer home_dir.close();
    return home_dir.openDir("zig-downloads", .{}) catch |err| switch (err) {
        error.FileNotFound => {
            try home_dir.makeDir("zig-downloads");
            return home_dir.openDir("zig-downloads", .{});
        },
        else => return err,
    };
}

// Will this be added to the stdlib someday?
fn openHomeDir() !std.fs.Dir {
    const uid = std.os.linux.getuid();
    const f = try std.fs.openFileAbsoluteZ("/etc/passwd", .{});
    defer f.close();
    const passwd = try f.readToEndAlloc(gpa, 10_000_000);
    defer gpa.free(passwd);

    var lines = std.mem.split(u8, passwd, "\n");
    while (lines.next()) |line| {
        if (line.len == 0) continue;
        // name:password:UID:GID:GECOS:directory:shell
        var fields = std.mem.split(u8, line, ":");
        _ = fields.next() orelse return error.UnexpectedEol; // name
        _ = fields.next() orelse return error.UnexpectedEol; // password
        const line_uid = fields.next() orelse return error.UnexpectedEol; // UID
        _ = fields.next() orelse return error.UnexpectedEol; // GID
        _ = fields.next() orelse return error.UnexpectedEol; // GECOS
        const line_direcotry = fields.next() orelse return error.UnexpectedEol; // directory
        _ = fields.next() orelse return error.UnexpectedEol; // shell
        if (fields.next() != null) return error.LineTooLong;

        if (uid == try std.fmt.parseInt(u32, line_uid, 10)) return std.fs.openDirAbsolute(line_direcotry, .{});
    }

    return error.UidNotFound;
}
