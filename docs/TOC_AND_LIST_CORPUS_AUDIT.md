# Translation structure corpus audit

This report is generated from `translate_tracking.json` and is read-only.
Flags are regression candidates, not proof of a visual defect: trackers do not retain source line geometry.

Trackers scanned: 72

| Book | TOC heading | Chapter list | Bullet list | Numbered run | Possible collapsed rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| `02_Mathematics_of_Machine_Learning_` | 12 | 0 | 236 | 146 | 119 |
| `2010_Modern_B-Tree_Techniques` | 44 | 0 | 164 | 75 | 44 |
| `2023_-_Data_Structures_for_Data-Intensive_Applications_T` | 11 | 0 | 36 | 37 | 15 |
| `2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai` | 14 | 0 | 5 | 357 | 316 |
| `Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_` | 6 | 16 | 0 | 108 | 65 |
| `Inference_Engineering` | 7 | 1 | 318 | 13 | 9 |
| `graph-engineering-v2026.08.02` | 3 | 0 | 614 | 193 | 27 |

## Representative candidates

- `02_Mathematics_of_Machine_Learning_` — **bullet-list** (`02_Mathematics_of_Machine_Learning_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 1.1 What is a vector space? . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 9 1.1.1 Examples of vector spaces • 11

- `02_Mathematics_of_Machine_Learning_` — **numbered-run** (`02_Mathematics_of_Machine_Learning_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 4.1.1 Linear transformations and matrices • 121 4.1.2 Matrix operations revisited • 123 4.1.3 Inverting linear transformations • 124 4.1.4 The kernel and the image • 127

- `02_Mathematics_of_Machine_Learning_` — **possible-collapsed-rows** (`02_Mathematics_of_Machine_Learning_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 6.1 Eigenvalues of matrices . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .. .. .. .. .. .. . . .. .. .. .. .. .. .. .. .. .. .. . 189 6.2 Finding eigenvalue-eigenvector pairs . . . . . . . . . . . . . . . . .. .. .. .. .. .. .. .. .. .. .. .. .. .. .. .. .. .. .. . 191 6.2.1 The characteristic polynomial • 192 6.2.2 Finding eigenvectors • 

- `02_Mathematics_of_Machine_Learning_` — **toc-heading** (`02_Mathematics_of_Machine_Learning_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): Table of Contents

- `2010_Modern_B-Tree_Techniques` — **bullet-list** (`2010_Modern_B-Tree_Techniques/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): • B-trees are indexes optimized for paged environments, i.e., storage not supporting byte access. A B-tree node occupies a page or asetofcontiguous pages. Access to individual records requires a buffer pool in byte-addressable storage such as RAM.

- `2010_Modern_B-Tree_Techniques` — **numbered-run** (`2010_Modern_B-Tree_Techniques/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 3.1 Node Size 232 3.2 Interpolation Search 233 3.3 Variable-length Records 235 3.4 NormalizedKeys 237 3.5 Prefix B-trees 239 3.6 CPU Caches 244

- `2010_Modern_B-Tree_Techniques` — **possible-collapsed-rows** (`2010_Modern_B-Tree_Techniques/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 5.1 Disk-order Scans 309 5.2 FetchingRows 312 5.3 CoveringIndexes 313 5.4 Index-to-index Navigation 317 5.5 Exploiting Key Prefixes 324 5.6 OrderedRetrieval 327 5.7 Multiple Indexes for aSingleTable 329 5.8 Multiple Tables in aSingleIndex 333 5.9 NestedQueries and Nested Iteration 334 5.10 Update Plans 337

- `2010_Modern_B-Tree_Techniques` — **toc-heading** (`2010_Modern_B-Tree_Techniques/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): a table in a database, it can be a pointer to a record with all those columns, or it can be anything else. In most parts of this survey, the nature, contents, and semantics of this information are not important and notdiscussed further.

- `2023_-_Data_Structures_for_Data-Intensive_Applications_T` — **bullet-list** (`2023_-_Data_Structures_for_Data-Intensive_Applications_T/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): • Chapter 7 discusses additional design considerations that can in- fluence the detailed deployment of data structures ranging from deploying data structures in a setting with concurrent execution, in the context of distributed systems, to new hardware, new type workloads, and new application requirements.

- `2023_-_Data_Structures_for_Data-Intensive_Applications_T` — **numbered-run** (`2023_-_Data_Structures_for_Data-Intensive_Applications_T/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): example, we canuse the first two bits of the 12-bit binary representation of the keys in our example data set: 25 = 0b000000011001, 49 = 0b000000110001, 200 = 0b000011001000, 230 = 0b000011100110, 242 = 0b000011110010, 1002 = 0b001111101020, 1500 = 0b010111011100, 2000 = 0b011111010000, and 2304 = 0b100100000000.

- `2023_-_Data_Structures_for_Data-Intensive_Applications_T` — **possible-collapsed-rows** (`2023_-_Data_Structures_for_Data-Intensive_Applications_T/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): example, we canuse the first two bits of the 12-bit binary representation of the keys in our example data set: 25 = 0b000000011001, 49 = 0b000000110001, 200 = 0b000011001000, 230 = 0b000011100110, 242 = 0b000011110010, 1002 = 0b001111101020, 1500 = 0b010111011100, 2000 = 0b011111010000, and 2304 = 0b100100000000.

- `2023_-_Data_Structures_for_Data-Intensive_Applications_T` — **toc-heading** (`2023_-_Data_Structures_for_Data-Intensive_Applications_T/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): Each application, or workload, can be represented as a mixture of key-value operations (point queries, range queries, inserts, deletes, and modifications) it supports over its data. In addition, the amount of memory and persistent storage required, along with their cost, shape the requirements of a given application. For example, file systems manage file met

- `2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai` — **bullet-list** (`2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): • Integrate full stack optimization techniques for robust, reliable AI system performance

- `2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai` — **numbered-run** (`2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): The CPU and GPU Superchip 23 NVIDIA Grace CPU 26 NVIDIA Blackwell “Dual-Die” GPU 26 NVIDIA GPU Tensor Cores and Transformer Engine 29 Streaming Multiprocessor, Threads, and Warps 31 Ultrascale Networking Treating Many GPUs as One 33 NVLink and NVSwitch 34 Multi-GPU Programming 38 In-Network Aggregations with NVIDIA SHARP 40

- `2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai` — **possible-collapsed-rows** (`2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): The CPU and GPU Superchip 23 NVIDIA Grace CPU 26 NVIDIA Blackwell “Dual-Die” GPU 26 NVIDIA GPU Tensor Cores and Transformer Engine 29 Streaming Multiprocessor, Threads, and Warps 31 Ultrascale Networking Treating Many GPUs as One 33 NVLink and NVSwitch 34 Multi-GPU Programming 38 In-Network Aggregations with NVIDIA SHARP 40

- `2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai` — **toc-heading** (`2025_-_AI_Systems_Performance_Engineering_Optimizing_Hardware_Software_and_Algorithms_for_Efficient_Trai/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): Table of Contents

- `Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_` — **chapter-cover-list** (`Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): This chapter covers

- `Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_` — **numbered-run** (`Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 2.1 Introducing LLMs for text generation 19 2.2 Setting up the coding environment 20 2.3 Understanding hardware needs and recommendations 23

- `Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_` — **possible-collapsed-rows** (`Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): 2.4 Preparing input texts for LLMs 25 2.5 Loading pretrained models 29 2.6 Understanding the sequential LLM text generation process 34 2.7 Coding a minimal text generation function 40 2.8 Faster inference via KV caching 46 2.9 Faster inference via PyTorch model compilation 50

- `Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_` — **toc-heading** (`Build_a_Reasoning_Model_From_Scratch_Sebastian_Raschka_/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): brief contents

- `Inference_Engineering` — **bullet-list** (`Inference_Engineering/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): • Batching: Run incoming requests in parallel, weaving them together on a token-by-token basis to increase throughput.

- `Inference_Engineering` — **chapter-cover-list** (`Inference_Engineering/chunk-2-pages-51-100/chunk-002-pages-51-100/translate_tracking.json`): The most common type of accelerator for inference is the GPU, and the market leader in GPUs for inference is NVIDIA. This book focuses on inference engineering for NVIDIA GPUs in the datacenter, but section 3.4 of this chapter covers other vendors of datacenter accelerators, and section 3.5 covers local inference.

- `Inference_Engineering` — **numbered-run** (`Inference_Engineering/chunk-3-pages-101-150/chunk-003-pages-101-150/translate_tracking.json`): Working with quantized data does introduce overhead, so it’s not linearly twice as fast to go from 16 to 8 bits. In practice, quantization down a single level of precision generally offers 30 to 50 percent better performance for LLMs.

- `Inference_Engineering` — **possible-collapsed-rows** (`Inference_Engineering/chunk-2-pages-51-100/chunk-002-pages-51-100/translate_tracking.json`): A lower temperature, top-k, or top-p makes LLM output more predictable as the model is constrained to selecting highly likely tokens. Setting the temperature to 0 or top-k to 1 makes token selection deterministic (always select the highest-probability token).

- `Inference_Engineering` — **toc-heading** (`Inference_Engineering/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): Table of Contents

- `graph-engineering-v2026.08.02` — **bullet-list** (`graph-engineering-v2026.08.02/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): • 실패 격리와 감사 가능한 라우팅이 필요하다

- `graph-engineering-v2026.08.02` — **numbered-run** (`graph-engineering-v2026.08.02/chunk-1-pages-1-50/chunk-001-pages-1-50/translate_tracking.json`): A 용어집 399 B 참고 링크 409 C Cypher ・ SPARQL ・ GQL대조 415 D 엔진 비교 419

- `graph-engineering-v2026.08.02` — **possible-collapsed-rows** (`graph-engineering-v2026.08.02/chunk-10-pages-451-453/chunk-010-pages-451-453/translate_tracking.json`): 연상 기억형 RAG, 57, 167 오케스트레이터-워커, 253 오프로딩, 241 위상 정렬, 15, 85 유효 시간, 157, 279 이름 붙인 그래프, 47 이벤트 소싱, 15, 317 이분 그래프, 67, 71 이중 시간, 157 인덱스, 357 인덱스 없는 인접성, 77 인접 리스트, 77 인접 행렬, 77 인접 행렬과 인접 리스트, 77 일괄 적재, 357 읽은 시점 기록, 303 잃어버린갱신, 329 임베디드그래프 엔진, 47 자기 일관성, 147 자기 학습 편향, 291 자기수정온톨로지, 385 장기 기억, 279 장기 기억 저장소, 241 재개 명령, 231 재귀 공통 테이블 식, 27 재귀 한도, 199 재생, 317 재

- `graph-engineering-v2026.08.02` — **toc-heading** (`graph-engineering-v2026.08.02/chunk-5-dual-retry/chunk-005-pages-201-250/translate_tracking.json`): • 조기 종료(early stopping) [사실상 표준] https://www.deeplearningbook.org/contents/regularization.html
