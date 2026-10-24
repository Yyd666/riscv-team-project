#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>

__attribute__((noinline))
int64_t kernel(const int32_t *left, const int32_t *right, unsigned int count)
{
    int64_t total = 0;
    for (unsigned int i = 0; i < count; ++i) {
        total += (int64_t)left[i] * (int64_t)right[i];
    }
    return total;
}

int main(void)
{
    unsigned int count;
    int32_t left[64] = {0};
    int32_t right[64] = {0};
    if (scanf("%u", &count) != 1 || count > 64) {
        return 2;
    }
    for (unsigned int i = 0; i < count; ++i) {
        if (scanf("%" SCNd32, &left[i]) != 1 || left[i] < -10000 || left[i] > 10000) {
            return 2;
        }
    }
    for (unsigned int i = 0; i < count; ++i) {
        if (scanf("%" SCNd32, &right[i]) != 1 || right[i] < -10000 || right[i] > 10000) {
            return 2;
        }
    }
    printf("%" PRId64 "\n", kernel(left, right, count));
    return 0;
}
