// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2026 C-NHXT-N and contributors
#include <cerrno>
#include <cstdio>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

int main() {
    void* region = mmap(nullptr, sizeof(int), PROT_READ | PROT_WRITE,
                        MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (region == MAP_FAILED) { std::perror("mmap"); return 1; }
    auto* value = static_cast<int*>(region);
    *value = 0;
    const pid_t child = fork();
    if (child == -1) { std::perror("fork"); munmap(region, sizeof(int)); return 1; }
    if (child == 0) { *value = 42; _exit(0); }
    int status = 0;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        munmap(region, sizeof(int)); return 1;
    }
    std::printf("shared value after child exit: %d\n", *value);
    const bool valid = *value == 42;
    return munmap(region, sizeof(int)) == 0 && valid ? 0 : 1;
}
