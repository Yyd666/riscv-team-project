#include <stdio.h>
#include <stdint.h>

__attribute__((noinline)) int64_t kernel(const int32_t *a, const int32_t *b, uint32_t count) {
    int64_t total = 0;
    for (uint32_t i = 0; i < count; ++i) total += (int64_t)a[i] * b[i];
    return total;
}

int main(void) {
    uint32_t n = 0; int32_t a[32] = {0}, b[32] = {0};
    if (scanf("%u", &n) != 1 || n > 32) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%d", &a[i]) != 1) return 2;
    for (uint32_t i = 0; i < n; ++i) if (scanf("%d", &b[i]) != 1) return 2;
    printf("%lld\n", (long long)kernel(a, b, n));
    return 0;
}
