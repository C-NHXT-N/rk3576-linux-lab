// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2026 C-NHXT-N and contributors
#include <cerrno>
#include <cstdio>
#include <sys/wait.h>
#include <unistd.h>

// A small message fits in a pipe; all reads and writes still check errors.
int main() {
    int descriptors[2];
    if (pipe(descriptors) == -1) { std::perror("pipe"); return 1; }
    const pid_t child = fork();
    if (child == -1) { std::perror("fork"); return 1; }
    if (child == 0) {
        close(descriptors[0]);
        const char message[] = "hello through pipe\n";
        size_t sent = 0;
        while (sent < sizeof(message) - 1) {
            const ssize_t count = write(descriptors[1], message + sent, sizeof(message) - 1 - sent);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) _exit(1);
            sent += static_cast<size_t>(count);
        }
        close(descriptors[1]);
        _exit(0);
    }
    close(descriptors[1]);
    char buffer[64];
    bool failed = false;
    while (true) {
        const ssize_t count = read(descriptors[0], buffer, sizeof(buffer));
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) { std::perror("read"); failed = true; break; }
        if (count == 0) break;
        if (std::fwrite(buffer, 1, static_cast<size_t>(count), stdout) != static_cast<size_t>(count)) {
            failed = true; break;
        }
    }
    close(descriptors[0]);
    int status = 0;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    return failed || waited < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ? 1 : 0;
}
