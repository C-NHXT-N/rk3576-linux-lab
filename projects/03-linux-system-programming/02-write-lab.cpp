// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2026 C-NHXT-N and contributors
#include <cerrno>
#include <cstdio>
#include <unistd.h>

int main()
{
    const char message[] = "Hello via write()\n";

    size_t sent = 0;
    while (sent < sizeof(message) - 1) {
        const ssize_t count = write(STDOUT_FILENO, message + sent, sizeof(message) - 1 - sent);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { std::perror("write"); return 1; }
        sent += static_cast<size_t>(count);
    }

    return 0;
}
