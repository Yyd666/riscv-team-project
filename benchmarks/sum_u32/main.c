#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline))
uint32_t kernel(const uint32_t *values, unsigned int count)
{
    uint32_t total = 0;
    for (unsigned int i = 0; i < count; ++i) {
        total += values[i];
    }
    return total;
}

int main(void)
{
    unsigned int count;
    uint32_t values[64] = {0};
    if (scanf("%u", &count) != 1 || count > 64) {
        return 2;
    }
    for (unsigned int i = 0; i < count; ++i) {
        if (scanf("%" SCNu32, &values[i]) != 1) {
            return 2;
        }
    }
    printf("%" PRIu32 "\n", kernel(values, count));
    return 0;
}
