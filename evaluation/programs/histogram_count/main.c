#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline)) uint32_t kernel(const uint32_t *values, uint32_t count) {
    uint32_t bins[8] = {0};
    for (uint32_t i = 0; i < count; ++i) ++bins[values[i]];
    uint32_t weighted = 0;
    for (uint32_t i = 0; i < 8; ++i) weighted += bins[i] * (i + 1);
    return weighted;
}

int main(void) {
    uint32_t count = 0, values[64] = {0};
    if (scanf("%" SCNu32, &count) != 1 || count > 64) return 2;
    for (uint32_t i = 0; i < count; ++i)
        if (scanf("%" SCNu32, &values[i]) != 1 || values[i] > 7) return 2;
    printf("%" PRIu32 "\n", kernel(values, count));
    return 0;
}
