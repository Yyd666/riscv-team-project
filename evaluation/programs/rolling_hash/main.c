#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline)) uint32_t kernel(const uint32_t *values, uint32_t count) {
    uint64_t hash = 0;
    for (uint32_t i = 0; i < count; ++i) hash = (hash * 257u + values[i]) % 1000000007u;
    return (uint32_t)hash;
}

int main(void) {
    uint32_t count = 0, values[64] = {0};
    if (scanf("%" SCNu32, &count) != 1 || count > 64) return 2;
    for (uint32_t i = 0; i < count; ++i)
        if (scanf("%" SCNu32, &values[i]) != 1 || values[i] > 255) return 2;
    printf("%" PRIu32 "\n", kernel(values, count));
    return 0;
}
