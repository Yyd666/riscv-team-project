#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline))
unsigned int kernel(const int32_t *values, unsigned int count, int32_t threshold)
{
    unsigned int matches = 0;
    for (unsigned int i = 0; i < count; ++i) {
        if (values[i] >= threshold) {
            ++matches;
        }
    }
    return matches;
}

int main(void)
{
    unsigned int count;
    int32_t threshold;
    int32_t values[64] = {0};
    if (scanf("%u %" SCNd32, &count, &threshold) != 2 || count > 64 ||
        threshold < -10000 || threshold > 10000) {
        return 2;
    }
    for (unsigned int i = 0; i < count; ++i) {
        if (scanf("%" SCNd32, &values[i]) != 1 || values[i] < -10000 || values[i] > 10000) {
            return 2;
        }
    }
    printf("%u\n", kernel(values, count, threshold));
    return 0;
}
