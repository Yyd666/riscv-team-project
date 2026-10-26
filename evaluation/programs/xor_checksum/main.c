#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) uint32_t kernel(const uint32_t *values, uint32_t count) {
    uint32_t result = 0;
    for (uint32_t i = 0; i < count; ++i) result ^= values[i];
    return result;
}

int main(void) {
    uint32_t n = 0, values[32] = {0};
    if (scanf("%u", &n) != 1 || n > 32) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%u", &values[i]) != 1) return 2;
    printf("%u\n", kernel(values, n));
    return 0;
}
