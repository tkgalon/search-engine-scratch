import os
import pickle
import contextlib
import heapq
import time
import math
import bisect

from index import InvertedIndexReader, InvertedIndexWriter
from util import IdMap, sorted_merge_posts_and_tfs
from compression import StandardPostings, VBEPostings
from trie import Trie, normalize_term
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable

class BSBIIndex:
    """
    Attributes
    ----------
    term_id_map(IdMap): Untuk mapping terms ke termIDs
    doc_id_map(IdMap): Untuk mapping relative paths dari dokumen (misal,
                    /collection/0/gamma.txt) to docIDs
    data_dir(str): Path ke data
    output_dir(str): Path ke output index files
    postings_encoding: Lihat di compression.py, kandidatnya adalah StandardPostings,
                    VBEPostings, dsb.
    index_name(str): Nama dari file yang berisi inverted index
    """
    def __init__(self, data_dir, output_dir, postings_encoding, index_name = "main_index"):
        self.term_id_map = IdMap()
        self.doc_id_map = IdMap()
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.index_name = index_name
        self.postings_encoding = postings_encoding

        # Untuk menyimpan nama-nama file dari semua intermediate inverted index
        self.intermediate_indices = []
        self.term_trie = None

    def save(self):
        """Menyimpan doc_id_map and term_id_map ke output directory via pickle"""

        with open(os.path.join(self.output_dir, 'terms.dict'), 'wb') as f:
            pickle.dump(self.term_id_map, f)
        with open(os.path.join(self.output_dir, 'docs.dict'), 'wb') as f:
            pickle.dump(self.doc_id_map, f)

    def load(self):
        """Memuat doc_id_map and term_id_map dari output directory"""

        with open(os.path.join(self.output_dir, 'terms.dict'), 'rb') as f:
            self.term_id_map = pickle.load(f)
        with open(os.path.join(self.output_dir, 'docs.dict'), 'rb') as f:
            self.doc_id_map = pickle.load(f)
        self.term_trie = None

    def build_term_trie(self):
        """
        Membangun Trie dari seluruh term yang ada pada term_id_map.
        Trie dibangun secara lazy dan menyimpan cached top suggestions
        berdasarkan document frequency agar autocomplete lebih berguna.
        """
        if len(self.term_id_map) == 0:
            self.load()

        aggregated_terms = {}
        with InvertedIndexReader(self.index_name, self.postings_encoding, directory=self.output_dir) as merged_index:
            for term_id, term in enumerate(self.term_id_map.id_to_str):
                normalized_term = normalize_term(term)
                if not normalized_term or term_id not in merged_index.postings_dict:
                    continue

                df = merged_index.postings_dict[term_id][1]
                is_clean_surface = term.isalnum()

                if normalized_term not in aggregated_terms:
                    aggregated_terms[normalized_term] = {
                        "display": term,
                        "display_rank": (1 if is_clean_surface else 0, df, -len(term), term),
                        "score": df,
                    }
                else:
                    aggregated_terms[normalized_term]["score"] += df
                    candidate_rank = (1 if is_clean_surface else 0, df, -len(term), term)
                    if candidate_rank > aggregated_terms[normalized_term]["display_rank"]:
                        aggregated_terms[normalized_term]["display"] = term
                        aggregated_terms[normalized_term]["display_rank"] = candidate_rank

        trie = Trie()
        for normalized_term, metadata in aggregated_terms.items():
            trie.insert(normalized_term, metadata["display"], metadata["score"])
        self.term_trie = trie
        return trie

    def autocomplete(self, prefix, k = 10):
        """
        Mengembalikan daftar term yang memiliki prefix tertentu.

        Parameters
        ----------
        prefix: str
            Prefix term yang ingin dilengkapi
        k: int
            Maksimum jumlah suggestion yang dikembalikan

        Result
        ------
        List[str]
            Daftar term hasil autocomplete secara leksikografis.
        """
        if prefix is None:
            return []

        prefix = prefix.strip()
        if len(prefix) == 0:
            return []

        if self.term_trie is None:
            self.build_term_trie()
        return self.term_trie.autocomplete(prefix, limit = k)

    def autocomplete_query(self, query, k = 10):
        """
        Mengembalikan saran autocomplete untuk token terakhir pada query.

        Parameters
        ----------
        query: str
            Query yang mungkin belum lengkap
        k: int
            Maksimum jumlah suggestion yang dikembalikan

        Result
        ------
        List[str]
            Daftar query lengkap hasil autocomplete.
        """
        if query is None:
            return []

        stripped_query = query.strip()
        if len(stripped_query) == 0:
            return []

        parts = stripped_query.split()
        prefix = parts[-1]
        prefix_suggestions = self.autocomplete(prefix, k = k)

        if len(parts) == 1:
            return prefix_suggestions

        query_prefix = " ".join(parts[:-1])
        return [query_prefix + " " + suggestion for suggestion in prefix_suggestions]

    def parse_block(self, block_dir_relative):
        """
        Lakukan parsing terhadap text file sehingga menjadi sequence of
        <termID, docID> pairs.

        Gunakan tools available untuk Stemming Bahasa Inggris

        JANGAN LUPA BUANG STOPWORDS!

        Untuk "sentence segmentation" dan "tokenization", bisa menggunakan
        regex atau boleh juga menggunakan tools lain yang berbasis machine
        learning.

        Parameters
        ----------
        block_dir_relative : str
            Relative Path ke directory yang mengandung text files untuk sebuah block.

            CATAT bahwa satu folder di collection dianggap merepresentasikan satu block.
            Konsep block di soal tugas ini berbeda dengan konsep block yang terkait
            dengan operating systems.

        Returns
        -------
        List[Tuple[Int, Int]]
            Returns all the td_pairs extracted from the block
            Mengembalikan semua pasangan <termID, docID> dari sebuah block (dalam hal
            ini sebuah sub-direktori di dalam folder collection)

        Harus menggunakan self.term_id_map dan self.doc_id_map untuk mendapatkan
        termIDs dan docIDs. Dua variable ini harus 'persist' untuk semua pemanggilan
        parse_block(...).
        """
        dir = "./" + self.data_dir + "/" + block_dir_relative
        td_pairs = []
        for filename in next(os.walk(dir))[2]:
            docname = dir + "/" + filename
            with open(docname, "r", encoding = "utf8", errors = "surrogateescape") as f:
                for token in f.read().split():
                    td_pairs.append((self.term_id_map[token], self.doc_id_map[docname]))

        return td_pairs

    def invert_write(self, td_pairs, index):
        """
        Melakukan inversion td_pairs (list of <termID, docID> pairs) dan
        menyimpan mereka ke index. Disini diterapkan konsep BSBI dimana 
        hanya di-mantain satu dictionary besar untuk keseluruhan block.
        Namun dalam teknik penyimpanannya digunakan srategi dari SPIMI
        yaitu penggunaan struktur data hashtable (dalam Python bisa
        berupa Dictionary)

        ASUMSI: td_pairs CUKUP di memori

        Di Tugas Pemrograman 1, kita hanya menambahkan term dan
        juga list of sorted Doc IDs. Sekarang di Tugas Pemrograman 2,
        kita juga perlu tambahkan list of TF.

        Parameters
        ----------
        td_pairs: List[Tuple[Int, Int]]
            List of termID-docID pairs
        index: InvertedIndexWriter
            Inverted index pada disk (file) yang terkait dengan suatu "block"
        """
        term_dict = {}
        term_tf = {}
        for term_id, doc_id in td_pairs:
            if term_id not in term_dict:
                term_dict[term_id] = set()
                term_tf[term_id] = {}
            term_dict[term_id].add(doc_id)
            if doc_id not in term_tf[term_id]:
                term_tf[term_id][doc_id] = 0
            term_tf[term_id][doc_id] += 1
        for term_id in sorted(term_dict.keys()):
            sorted_doc_id = sorted(list(term_dict[term_id]))
            assoc_tf = [term_tf[term_id][doc_id] for doc_id in sorted_doc_id]
            index.append(term_id, sorted_doc_id, assoc_tf)

    def merge(self, indices, merged_index):
        """
        Lakukan merging ke semua intermediate inverted indices menjadi
        sebuah single index.

        Ini adalah bagian yang melakukan EXTERNAL MERGE SORT

        Gunakan fungsi orted_merge_posts_and_tfs(..) di modul util

        Parameters
        ----------
        indices: List[InvertedIndexReader]
            A list of intermediate InvertedIndexReader objects, masing-masing
            merepresentasikan sebuah intermediate inveted index yang iterable
            di sebuah block.

        merged_index: InvertedIndexWriter
            Instance InvertedIndexWriter object yang merupakan hasil merging dari
            semua intermediate InvertedIndexWriter objects.
        """
        # kode berikut mengasumsikan minimal ada 1 term
        merged_iter = heapq.merge(*indices, key = lambda x: x[0])
        curr, postings, tf_list = next(merged_iter) # first item
        for t, postings_, tf_list_ in merged_iter: # from the second item
            if t == curr:
                zip_p_tf = sorted_merge_posts_and_tfs(list(zip(postings, tf_list)), \
                                                      list(zip(postings_, tf_list_)))
                postings = [doc_id for (doc_id, _) in zip_p_tf]
                tf_list = [tf for (_, tf) in zip_p_tf]
            else:
                merged_index.append(curr, postings, tf_list)
                curr, postings, tf_list = t, postings_, tf_list_
        merged_index.append(curr, postings, tf_list)

    def retrieve_tfidf(self, query, k = 10):
        """
        Melakukan Ranked Retrieval dengan skema TaaT (Term-at-a-Time).
        Method akan mengembalikan top-K retrieval results.

        w(t, D) = (1 + log tf(t, D))       jika tf(t, D) > 0
                = 0                        jika sebaliknya

        w(t, Q) = IDF = log (N / df(t))

        Score = untuk setiap term di query, akumulasikan w(t, Q) * w(t, D).
                (tidak perlu dinormalisasi dengan panjang dokumen)

        catatan: 
            1. informasi DF(t) ada di dictionary postings_dict pada merged index
            2. informasi TF(t, D) ada di tf_li
            3. informasi N bisa didapat dari doc_length pada merged index, len(doc_length)

        Parameters
        ----------
        query: str
            Query tokens yang dipisahkan oleh spasi

            contoh: Query "universitas indonesia depok" artinya ada
            tiga terms: universitas, indonesia, dan depok

        Result
        ------
        List[(int, str)]
            List of tuple: elemen pertama adalah score similarity, dan yang
            kedua adalah nama dokumen.
            Daftar Top-K dokumen terurut mengecil BERDASARKAN SKOR.

        JANGAN LEMPAR ERROR/EXCEPTION untuk terms yang TIDAK ADA di collection.

        """
        if len(self.term_id_map) == 0 or len(self.doc_id_map) == 0:
            self.load()

        terms = [self.term_id_map[word] for word in query.split()]
        with InvertedIndexReader(self.index_name, self.postings_encoding, directory=self.output_dir) as merged_index:

            scores = {}
            for term in terms:
                if term in merged_index.postings_dict:
                    df = merged_index.postings_dict[term][1]
                    N = len(merged_index.doc_length)
                    postings, tf_list = merged_index.get_postings_list(term)
                    for i in range(len(postings)):
                        doc_id, tf = postings[i], tf_list[i]
                        if doc_id not in scores:
                            scores[doc_id] = 0
                        if tf > 0:
                            scores[doc_id] += math.log(N / df) * (1 + math.log(tf))

            # Top-K
            docs = [(score, self.doc_id_map[doc_id]) for (doc_id, score) in scores.items()]
            return sorted(docs, key = lambda x: x[0], reverse = True)[:k]

    def retrieve_bm25(self, query, k = 10, k1 = 1.2, b = 0.75):
        """
        Melakukan Ranked Retrieval dengan skema BM25 menggunakan pendekatan TaaT.

        Score = sum_t IDF(t) * ((tf(t, D) * (k1 + 1)) /
                (tf(t, D) + k1 * (1 - b + b * dl / avgdl)))

        dengan IDF(t) = log(1 + ((N - df(t) + 0.5) / (df(t) + 0.5)))

        Parameters
        ----------
        query: str
            Query tokens yang dipisahkan oleh spasi
        k: int
            Banyaknya dokumen yang dikembalikan
        k1: float
            Parameter BM25 untuk mengontrol saturasi TF
        b: float
            Parameter BM25 untuk normalisasi panjang dokumen

        Result
        ------
        List[(float, str)]
            List of tuple: elemen pertama adalah score similarity, dan yang
            kedua adalah nama dokumen. Daftar Top-K dokumen terurut mengecil
            berdasarkan skor.
        """
        if len(self.term_id_map) == 0 or len(self.doc_id_map) == 0:
            self.load()

        query_terms = [self.term_id_map.str_to_id[word]
                       for word in query.split()
                       if word in self.term_id_map.str_to_id]

        with InvertedIndexReader(self.index_name, self.postings_encoding, directory=self.output_dir) as merged_index:
            N = len(merged_index.doc_length)
            avgdl = merged_index.avg_doc_length
            if N == 0 or avgdl == 0:
                return []

            scores = {}
            for term in query_terms:
                if term not in merged_index.postings_dict:
                    continue

                df = merged_index.postings_dict[term][1]
                postings, tf_list = merged_index.get_postings_list(term)
                idf = math.log(1 + ((N - df + 0.5) / (df + 0.5)))

                for i in range(len(postings)):
                    doc_id, tf = postings[i], tf_list[i]
                    dl = merged_index.doc_length[doc_id]
                    denominator = tf + k1 * (1 - b + b * dl / avgdl)
                    score = idf * ((tf * (k1 + 1)) / denominator)
                    if doc_id not in scores:
                        scores[doc_id] = 0
                    scores[doc_id] += score

            docs = [(score, self.doc_id_map[doc_id]) for (doc_id, score) in scores.items()]
            return sorted(docs, key = lambda x: x[0], reverse = True)[:k]

    def retrieve_bm25_wand(self, query, k = 10, k1 = 1.2, b = 0.75):
        """
        Melakukan Top-K retrieval BM25 dengan algoritma WAND.

        WAND menggunakan upper bound score per term untuk menghindari
        perhitungan skor BM25 penuh pada semua dokumen kandidat.

        Parameters
        ----------
        query: str
            Query tokens yang dipisahkan oleh spasi
        k: int
            Banyaknya dokumen yang dikembalikan
        k1: float
            Parameter BM25 untuk mengontrol saturasi TF
        b: float
            Parameter BM25 untuk normalisasi panjang dokumen

        Result
        ------
        List[(float, str)]
            List of tuple: elemen pertama adalah score similarity, dan yang
            kedua adalah nama dokumen. Daftar Top-K dokumen terurut mengecil
            berdasarkan skor.
        """
        if len(self.term_id_map) == 0 or len(self.doc_id_map) == 0:
            self.load()

        query_terms = [self.term_id_map.str_to_id[word]
                       for word in query.split()
                       if word in self.term_id_map.str_to_id]

        with InvertedIndexReader(self.index_name, self.postings_encoding, directory=self.output_dir) as merged_index:
            N = len(merged_index.doc_length)
            avgdl = merged_index.avg_doc_length
            if N == 0 or avgdl == 0:
                return []

            cursors = []
            for term in query_terms:
                if term not in merged_index.postings_dict:
                    continue

                df = merged_index.postings_dict[term][1]
                max_tf = merged_index.postings_dict[term][4]
                postings, tf_list = merged_index.get_postings_list(term)
                if len(postings) == 0:
                    continue

                idf = math.log(1 + ((N - df + 0.5) / (df + 0.5)))
                upper_bound = idf * ((max_tf * (k1 + 1)) / (max_tf + k1 * (1 - b)))
                cursors.append({
                    "term": term,
                    "postings": postings,
                    "tf_list": tf_list,
                    "idf": idf,
                    "upper_bound": upper_bound,
                    "pos": 0,
                })

            if len(cursors) == 0:
                return []

            top_k = []
            threshold = 0.0

            while True:
                active = [cursor for cursor in cursors if cursor["pos"] < len(cursor["postings"])]
                if len(active) == 0:
                    break

                active.sort(key = lambda cursor: cursor["postings"][cursor["pos"]])
                upper_bound_sum = 0.0
                pivot_idx = None
                pivot_doc = None

                for i, cursor in enumerate(active):
                    upper_bound_sum += cursor["upper_bound"]
                    if upper_bound_sum > threshold:
                        pivot_idx = i
                        pivot_doc = cursor["postings"][cursor["pos"]]
                        break

                if pivot_idx is None:
                    break

                smallest_doc = active[0]["postings"][active[0]["pos"]]
                if smallest_doc == pivot_doc:
                    candidate_doc = pivot_doc
                    score = 0.0

                    for cursor in active:
                        if cursor["postings"][cursor["pos"]] == candidate_doc:
                            tf = cursor["tf_list"][cursor["pos"]]
                            dl = merged_index.doc_length[candidate_doc]
                            denominator = tf + k1 * (1 - b + b * dl / avgdl)
                            score += cursor["idf"] * ((tf * (k1 + 1)) / denominator)
                            cursor["pos"] += 1

                    if len(top_k) < k:
                        heapq.heappush(top_k, (score, candidate_doc))
                    elif score > top_k[0][0]:
                        heapq.heapreplace(top_k, (score, candidate_doc))

                    if len(top_k) == k:
                        threshold = top_k[0][0]
                else:
                    for cursor in active[:pivot_idx]:
                        postings = cursor["postings"]
                        cursor["pos"] = bisect.bisect_left(postings, pivot_doc, cursor["pos"])

            docs = [(score, self.doc_id_map[doc_id]) for (score, doc_id) in top_k]
            return sorted(docs, key = lambda x: x[0], reverse = True)

    def index(self):
        """
        Base indexing code
        BAGIAN UTAMA untuk melakukan Indexing dengan skema BSBI (blocked-sort
        based indexing)

        Method ini scan terhadap semua data di collection, memanggil parse_block
        untuk parsing dokumen dan memanggil invert_write yang melakukan inversion
        di setiap block dan menyimpannya ke index yang baru.
        """
        # loop untuk setiap sub-directory di dalam folder collection (setiap block)
        for block_dir_relative in tqdm(sorted(next(os.walk(self.data_dir))[1])):
            td_pairs = self.parse_block(block_dir_relative)
            index_id = 'intermediate_index_'+block_dir_relative
            self.intermediate_indices.append(index_id)
            with InvertedIndexWriter(index_id, self.postings_encoding, directory = self.output_dir) as index:
                self.invert_write(td_pairs, index)
                td_pairs = None
    
        self.save()

        with InvertedIndexWriter(self.index_name, self.postings_encoding, directory = self.output_dir) as merged_index:
            with contextlib.ExitStack() as stack:
                indices = [stack.enter_context(InvertedIndexReader(index_id, self.postings_encoding, directory=self.output_dir))
                               for index_id in self.intermediate_indices]
                self.merge(indices, merged_index)


if __name__ == "__main__":

    BSBI_instance = BSBIIndex(data_dir = 'collection', \
                              postings_encoding = VBEPostings, \
                              output_dir = 'index')
    BSBI_instance.index() # memulai indexing!
