#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline)) uint32_t kernel(const uint32_t *values, uint32_t count) {
    if (count == 0) return 0;
    uint32_t best = 1, current = 1;
    for (uint32_t i = 1; i < count; ++i) {
        current = values[i] == values[i - 1] ? current + 1 : 1;
        if (current > best) best = current;
    }
    return best;
}

int main(void) {
    uint32_t count = 0, values[64] = {0};
    if (scanf("%" SCNu32, &count) != 1 || count > 64) return 2;
    for (uint32_t i = 0; i < count; ++i)
        if (scanf("%" SCNu32, &values[i]) != 1 || values[i] > 15) return 2;
    printf("%" PRIu32 "\n", kernel(values, count));
    return 0;
}
