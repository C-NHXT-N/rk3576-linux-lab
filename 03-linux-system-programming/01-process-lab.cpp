// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2026 C-NHXT-N and contributors
#include <iostream>
#include <unistd.h>

int main()
{
    std::cout << "Hello from RK3576!" << std::endl;

    std::cout << "PID  = " << getpid() << std::endl;
    std::cout << "PPID = " << getppid() << std::endl;

    std::cout << "Sleeping for 30 seconds..." << std::endl;

    sleep(30);

    std::cout << "Process exiting." << std::endl;

    return 0;
}
