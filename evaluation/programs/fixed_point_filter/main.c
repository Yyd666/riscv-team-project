#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) int64_t kernel(const int32_t *values, uint32_t count, int32_t threshold) {
    int64_t total = 0;
    for (uint32_t i = 0; i < count; ++i) {
        if (values[i] >= threshold) total += ((int64_t)values[i] * 3) / 2;
    }
    return total;
}

int main(void) {
    uint32_t n = 0; int32_t threshold = 0, values[32] = {0};
    if (scanf("%d %u", &threshold, &n) != 2 || n > 32) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%d", &values[i]) != 1) return 2;
    printf("%lld\n", (long long)kernel(values, n, threshold));
    return 0;
}
