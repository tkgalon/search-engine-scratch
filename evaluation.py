import re
import math
from bsbi import BSBIIndex
from compression import VBEPostings

######## >>>>> sebuah IR metric: RBP p = 0.8

def rbp(ranking, p = 0.8):
  """ menghitung search effectiveness metric score dengan 
      Rank Biased Precision (RBP)

      Parameters
      ----------
      ranking: List[int]
         vektor biner seperti [1, 0, 1, 1, 1, 0]
         gold standard relevansi dari dokumen di rank 1, 2, 3, dst.
         Contoh: [1, 0, 1, 1, 1, 0] berarti dokumen di rank-1 relevan,
                 di rank-2 tidak relevan, di rank-3,4,5 relevan, dan
                 di rank-6 tidak relevan
        
      Returns
      -------
      Float
        score RBP
  """
  score = 0.
  for i in range(1, len(ranking)):
    pos = i - 1
    score += ranking[pos] * (p ** (i - 1))
  return (1 - p) * score

def dcg(ranking):
  """
    Menghitung Discounted Cumulative Gain (DCG) dari ranking biner.
  """
  score = 0.
  for i in range(1, len(ranking) + 1):
    rel_i = ranking[i - 1]
    score += rel_i / math.log2(i + 1)
  return score

def ndcg(ranking):
  """
    Menghitung Normalized Discounted Cumulative Gain (NDCG) dari ranking biner.
  """
  actual_dcg = dcg(ranking)
  ideal_ranking = sorted(ranking, reverse = True)
  ideal_dcg = dcg(ideal_ranking)
  if ideal_dcg == 0:
    return 0.
  return actual_dcg / ideal_dcg

def ap(ranking):
  """
    Menghitung Average Precision (AP) dari ranking biner.
  """
  num_relevant = 0
  precision_sum = 0.

  for i in range(1, len(ranking) + 1):
    if ranking[i - 1] == 1:
      num_relevant += 1
      precision_sum += num_relevant / i

  if num_relevant == 0:
    return 0.
  return precision_sum / num_relevant


######## >>>>> memuat qrels

def load_qrels(qrel_file = "qrels.txt", max_q_id = 30, max_doc_id = 1033):
  """ memuat query relevance judgment (qrels) 
      dalam format dictionary of dictionary
      qrels[query id][document id]

      dimana, misal, qrels["Q3"][12] = 1 artinya Doc 12
      relevan dengan Q3; dan qrels["Q3"][10] = 0 artinya
      Doc 10 tidak relevan dengan Q3.

  """
  qrels = {"Q" + str(i) : {i:0 for i in range(1, max_doc_id + 1)} \
                 for i in range(1, max_q_id + 1)}
  with open(qrel_file) as file:
    for line in file:
      parts = line.strip().split()
      qid = parts[0]
      did = int(parts[1])
      qrels[qid][did] = 1
  return qrels

######## >>>>> EVALUASI !

def _eval_with_retriever(qrels, retrieve_fn, label, query_file = "queries.txt", k = 1000):
  """
    Helper internal untuk mengevaluasi satu metode retrieval terhadap semua query.
  """
  BSBI_instance = BSBIIndex(data_dir = 'collection', \
                          postings_encoding = VBEPostings, \
                          output_dir = 'index')

  with open(query_file) as file:
    rbp_scores = []
    dcg_scores = []
    ndcg_scores = []
    ap_scores = []
    for qline in file:
      parts = qline.strip().split()
      qid = parts[0]
      query = " ".join(parts[1:])

      # HATI-HATI, doc id saat indexing bisa jadi berbeda dengan doc id
      # yang tertera di qrels
      ranking = []
      for (score, doc) in retrieve_fn(BSBI_instance, query, k):
          did = int(re.search(r'\/.*\/.*\/(.*)\.txt', doc).group(1))
          ranking.append(qrels[qid][did])
      rbp_scores.append(rbp(ranking))
      dcg_scores.append(dcg(ranking))
      ndcg_scores.append(ndcg(ranking))
      ap_scores.append(ap(ranking))

  print(f"Hasil evaluasi {label} terhadap 30 queries")
  print("RBP score =", sum(rbp_scores) / len(rbp_scores))
  print("DCG score =", sum(dcg_scores) / len(dcg_scores))
  print(f"NDCG@{k} score =", sum(ndcg_scores) / len(ndcg_scores))
  print("AP score =", sum(ap_scores) / len(ap_scores))

def eval_tfidf(qrels, query_file = "queries.txt", k = 1000):
  """
    Evaluasi TF-IDF terhadap seluruh query.
  """
  _eval_with_retriever(
      qrels,
      lambda bsbi, query, k: bsbi.retrieve_tfidf(query, k = k),
      "TF-IDF",
      query_file = query_file,
      k = k
  )

def eval_bm25(qrels, query_file = "queries.txt", k = 1000):
  """
    Evaluasi BM25 terhadap seluruh query.
  """
  _eval_with_retriever(
      qrels,
      lambda bsbi, query, k: bsbi.retrieve_bm25(query, k = k),
      "BM25",
      query_file = query_file,
      k = k
  )

def eval(qrels, query_file = "queries.txt", k = 1000):
  """
    Backward-compatible alias untuk evaluasi TF-IDF.
  """
  eval_tfidf(qrels, query_file = query_file, k = k)

if __name__ == '__main__':
  qrels = load_qrels()

  assert qrels["Q1"][166] == 1, "qrels salah"
  assert qrels["Q1"][300] == 0, "qrels salah"
  assert abs(dcg([1, 0, 1, 1]) - (1 / math.log2(2) + 1 / math.log2(4) + 1 / math.log2(5))) < 1e-9, "dcg salah"
  assert ndcg([1, 1, 1]) == 1.0, "ndcg salah"
  assert ndcg([0, 0, 0]) == 0.0, "ndcg salah"
  assert ap([0, 0, 0]) == 0.0, "ap salah"
  assert abs(ap([1, 0, 1, 1]) - ((1 / 1) + (2 / 3) + (3 / 4)) / 3) < 1e-9, "ap salah"

  eval_tfidf(qrels)
  print()
  eval_bm25(qrels)
