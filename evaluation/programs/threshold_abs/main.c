#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) uint32_t kernel(const int32_t *values, uint32_t count, int32_t threshold) {
    uint32_t total = 0;
    for (uint32_t i = 0; i < count; ++i) {
        int64_t value = values[i];
        if ((value < 0 ? -value : value) >= threshold) ++total;
    }
    return total;
}

int main(void) {
    uint32_t n = 0; int32_t threshold = 0, values[32] = {0};
    if (scanf("%d %u", &threshold, &n) != 2 || n > 32 || threshold < 0) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%d", &values[i]) != 1) return 2;
    printf("%u\n", kernel(values, n, threshold));
    return 0;
}
