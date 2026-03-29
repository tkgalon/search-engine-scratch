# Search Engine From Scratch

This project implements a search engine from scratch with BSBI and SPIMI indexing pipelines. It supports multiple ranking methods (TF-IDF, BM25, BM25 WAND), evaluation metrics (RBP, DCG, NDCG, AP), Elias-Gamma compression for efficient storage, and Trie-based autocomplete for query suggestions.

## Project Structure

```text
├── collection/              # document collection
├── index/                   # BSBI-based index output
├── spimi_index/             # SPIMI-based index output
├── tmp/                     # temporary directory
├── bsbi.py                  # BSBI indexing and retrieval
├── spimi.py                 # SPIMI indexing mode
├── search.py                # retrieval demo using BSBI index
├── search_spimi.py          # retrieval demo using SPIMI index
├── evaluation.py            # evaluation script
├── compression.py           # postings compression methods
├── index.py                 # inverted index reader/writer
├── trie.py                  # Trie implementation for autocomplete
├── autocomplete.py          # autocomplete demo
├── util.py                  # helper utilities
├── queries.txt              # query set
└── qrels.txt                # relevance judgments
```

## How to Run

Run every command from the project root directory.

### Main Features

```bash
python3 compression.py
```

Runs a small encode/decode demo for `StandardPostings`, `VBEPostings`, and `EliasGammaPostings`.

```bash
python3 bsbi.py
```

Builds the main inverted index in `index/` using the BSBI pipeline.

```bash
python3 search.py
```

Runs retrieval examples on the BSBI index using:

- TF-IDF
- BM25
- BM25 WAND

```bash
python3 evaluation.py
```

Evaluates TF-IDF and BM25 using:

- RBP
- DCG
- NDCG
- AP

### Add-ons Features

```bash
python3 spimi.py
```

Builds a separate inverted index in `spimi_index/` using the SPIMI pipeline.

```bash
python3 search_spimi.py
```

Runs retrieval examples on the SPIMI-built index using:

- TF-IDF
- BM25
- BM25 WAND

```bash
python3 autocomplete.py
```

Runs the Trie-based autocomplete demo for both term completion and query completion.

# Implemented Features

## 1. Elias-Gamma Bit-Level Compression

`compression.py` was extended with a new compression class called `EliasGammaPostings`.

This method works at the bit level because each integer is first converted into an Elias-Gamma bitstring, and the resulting bitstream is then packed into bytes for storage. Unlike standard byte-based encoding, Elias-Gamma uses variable-length binary codes directly.

In this implementation:

- postings lists are converted into gap-based form before encoding
- term frequencies are encoded as positive integers
- the first gap value is shifted by `+1` during encoding and shifted back by `-1` during decoding, because document IDs in this codebase may start from `0`
- decoding reconstructs the original postings list from the stored gaps

As a result, the project now supports three compression methods:

- `StandardPostings`
- `VBEPostings`
- `EliasGammaPostings`

## 2. BM25 Scoring

A BM25-based retrieval method was added in `bsbi.py` through `retrieve_bm25(...)`, while the original `retrieve_tfidf(...)` was kept unchanged.

To support BM25, the index metadata in `index.py` now stores:

- `doc_length`
- `avg_doc_length`

These values are computed during indexing and later used for document-length normalization in BM25.

The BM25 implementation was tested using two IDF variants:

### BM25 Classic

The classic form uses:

```text
log((N - df + 0.5) / (df + 0.5))
```

Output:

- TF-IDF: `RBP score = 0.5979871614730231`
- BM25: `RBP score = 0.42502814692203655`

### BM25 with Non-Negative IDF Variant

The final implementation uses:

```text
log(1 + (N - df + 0.5) / (df + 0.5))
```

This variant avoids negative IDF values for very frequent terms and gives better performance on this collection.

Output:

- TF-IDF: `RBP score = 0.5979871614730231`
- BM25: `RBP score = 0.6317389568514513`

From this comparison, the non-negative IDF variant performs better than both TF-IDF and the classic BM25 formulation on the current dataset.

## 3. Additional Evaluation Metrics

`evaluation.py` was extended with three additional evaluation metrics:

- `DCG`
- `NDCG`
- `AP`

The system now evaluates retrieval results using:

- `RBP`
- `DCG`
- `NDCG@1000`
- `AP`

These metrics are computed for both TF-IDF and BM25 using the same qrels and query set.

### Evaluation Output

#### TF-IDF

```text
Hasil evaluasi TF-IDF terhadap 30 queries
RBP score = 0.5979871614730231
DCG score = 5.593507640705594
NDCG@1000 score = 0.7827272396968642
AP score = 0.4948315542516782
```

#### BM25

```text
Hasil evaluasi BM25 terhadap 30 queries
RBP score = 0.6317389568514513
DCG score = 5.744618450134211
NDCG@1000 score = 0.7930848027920508
AP score = 0.5144200180617612
```

Based on these results, BM25 outperforms TF-IDF on all reported evaluation metrics in the current implementation.

## 4. WAND Top-K Retrieval for BM25

BM25 retrieval was further extended with a WAND-based top-k method, implemented as `retrieve_bm25_wand(...)` in `bsbi.py`.

Instead of scoring every candidate document fully, this method uses per-term upper bounds to skip documents that are unlikely to appear in the final top-k results.

To support this, the inverted index metadata in `index.py` was also adjusted. In addition to the previous metadata, each term now stores:

- `max_tf_in_list`

This value is used to estimate an upper bound contribution of a term to the BM25 score, which is then used during WAND pivot selection and pruning.

The implementation was verified by checking that:

- `retrieve_bm25(...)` and `retrieve_bm25_wand(...)` return the same top-k results
- WAND uses the extra metadata stored in the inverted index

# Add-ons Features

## 5. SPIMI Indexing Mode

Besides the main BSBI pipeline, the project now also includes a standalone SPIMI-based indexing mode in `spimi.py` through the `SPIMIIndex` class.

This class inherits from `BSBIIndex`, but overrides the indexing process so that each block is inverted directly into an in-memory dictionary without first building a large `td_pairs` list. For each block, the implementation:

- reads documents one by one
- maps each token into a `term_id`
- updates an in-memory structure of the form `term_id -> {doc_id: tf}`
- writes the intermediate index in sorted term order

After all blocks are processed, the intermediate indices are merged into a final index with the same format as the regular BSBI pipeline.

Because of this design, the SPIMI output remains compatible with:

- `InvertedIndexReader`
- `retrieve_tfidf(...)`
- `retrieve_bm25(...)`
- `retrieve_bm25_wand(...)`

The SPIMI index is stored separately in `spimi_index/`, so it does not interfere with the main required implementation in `index/`.

An additional demo script, `search_spimi.py`, was also added to test retrieval on the SPIMI-built index.

The implementation was verified by checking that:

- `python3 spimi.py` successfully builds the SPIMI index
- the resulting index still stores `doc_length`, `avg_doc_length`, and `max_tf_in_list`
- retrieval results from SPIMI are consistent with the existing BSBI-based pipeline
- evaluation scores on the SPIMI index remain the same as the regular index

## 6. Trie-Based Dictionary and Autocomplete

The project also supports prefix-based interaction through a Trie-backed vocabulary structure. This feature is used to generate term suggestions and query completions from incomplete input.

To make the suggestions more useful, the Trie implementation also includes:

- normalized prefix matching
- cached top suggestions at each node
- ranking based on term strength in the collection, instead of simple alphabetical traversal

This feature was integrated into `BSBIIndex` through:

- `autocomplete(prefix, k=10)`
- `autocomplete_query(query, k=10)`

An additional demo script, `autocomplete.py`, was added to show how the feature works directly on the indexed collection.

### Demo Output

Example term autocomplete:

```text
Prefix : preg
['pregnancy', 'pregnant', 'pregnanediol', 'pregnanetriol', 'preg-', 'preganediol', 'pregnancies.']

Prefix : meta
['metabolism', 'metabolic', 'metastases', 'metastatic', 'metal', 'metabolites', 'metastasis', 'metals', 'metaphase', 'metabolize']
```

Example query autocomplete:

```text
Query  : lipid meta
['lipid metabolism', 'lipid metabolic', 'lipid metastases', 'lipid metastatic', 'lipid metal', 'lipid metabolites', 'lipid metastasis', 'lipid metals', 'lipid metaphase', 'lipid metabolize']

Query  : psychodr
['psychodrama']
```

The implementation was verified by checking that:

- Trie-based suggestions are returned correctly for term prefixes and incomplete queries
- the autocomplete feature works on top of the indexed vocabulary
- the existing required retrieval features remain unchanged
