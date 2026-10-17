#include <unistd.h>

int main()
{
    const char message[] = "Hello via write()\n";

    write(STDOUT_FILENO, message, sizeof(message) - 1);

    return 0;
}
