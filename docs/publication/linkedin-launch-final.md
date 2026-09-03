For a backend project I’m working on, Go was one of the leading candidates. But instead of relying on “Go is faster than Python,” I wanted to measure the practical difference under production-inspired POS workloads.

- CARD @100 median p95: ~2.96 s on Python vs ~156 ms on Go.
- 50,000-device Worker: ~27.00 s on Python vs ~10.15 s on Go.

The results support evaluating a broader Go migration, but they also showed that runtime choice alone isn’t enough: both implementations missed the <5 s Worker target. Query count, batching, database round trips, and architecture still matter.

Full write-up:
https://medium.com/@ferhatsli/python-vs-go-pos-backend-benchmark-results-from-500-to-50-000-devices-c5ce0218d7dd

Benchmark:
https://github.com/ferhatsli/python-vs-go-pos-benchmark

---

Üzerinde çalıştığım bir backend projesinde Go öne çıkan adaylardan biriydi. Ama “Go Python’dan daha hızlı” demek yerine, gerçek sisteme benzeyen POS workload’larında farkın ne kadar açıldığını ölçmek istedim.

- CARD @100 median p95: ~2,96 sn Python vs ~156 ms Go.
- 50.000 cihazlık Worker: ~27,00 sn Python vs ~10,15 sn Go.

Sonuçlar daha geniş bir Go migration’ını değerlendirmeyi destekliyor, fakat runtime değişikliğinin tek başına yeterli olmadığını da gösteriyor: iki taraf da Worker için <5 sn hedefini kaçırdı. Query count, batching, database round-trip sayısı ve architecture hâlâ önemli.

Detaylı yazı:
https://medium.com/@ferhatsli/python-vs-go-pos-backend-benchmark-results-from-500-to-50-000-devices-c5ce0218d7dd

Benchmark:
https://github.com/ferhatsli/python-vs-go-pos-benchmark
