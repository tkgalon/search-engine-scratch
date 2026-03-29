import os
import contextlib

from bsbi import BSBIIndex
from index import InvertedIndexReader, InvertedIndexWriter
from compression import VBEPostings

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable


class SPIMIIndex(BSBIIndex):
    """
    SPIMI-based indexer yang menghasilkan format inverted index yang sama
    dengan BSBIIndex, sehingga tetap kompatibel dengan retrieval dan evaluasi
    yang sudah ada.
    """

    def invert_write_spimi(self, block_dir_relative, index):
        """
        Membangun dictionary postings langsung di memori untuk satu block tanpa
        membuat list besar td_pairs, lalu menuliskannya ke disk.

        Parameters
        ----------
        block_dir_relative: str
            Nama subdirektori block di dalam collection.
        index: InvertedIndexWriter
            Writer untuk intermediate index block tersebut.
        """
        block_dir = "./" + self.data_dir + "/" + block_dir_relative
        term_dict = {}

        for filename in next(os.walk(block_dir))[2]:
            docname = block_dir + "/" + filename
            doc_id = self.doc_id_map[docname]

            with open(docname, "r", encoding="utf8", errors="surrogateescape") as f:
                for token in f.read().split():
                    term_id = self.term_id_map[token]
                    if term_id not in term_dict:
                        term_dict[term_id] = {}
                    if doc_id not in term_dict[term_id]:
                        term_dict[term_id][doc_id] = 0
                    term_dict[term_id][doc_id] += 1

        for term_id in sorted(term_dict.keys()):
            doc_tf = term_dict[term_id]
            postings_list = sorted(doc_tf.keys())
            tf_list = [doc_tf[doc_id] for doc_id in postings_list]
            index.append(term_id, postings_list, tf_list)

    def index(self):
        """
        Melakukan indexing dengan gaya SPIMI per block, lalu menggabungkan
        intermediate indices menjadi satu merged index final.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        self.intermediate_indices = []

        for block_dir_relative in tqdm(sorted(next(os.walk(self.data_dir))[1])):
            index_id = "intermediate_index_" + block_dir_relative
            self.intermediate_indices.append(index_id)

            with InvertedIndexWriter(index_id, self.postings_encoding, directory=self.output_dir) as index:
                self.invert_write_spimi(block_dir_relative, index)

        self.save()

        with InvertedIndexWriter(self.index_name, self.postings_encoding, directory=self.output_dir) as merged_index:
            with contextlib.ExitStack() as stack:
                indices = [
                    stack.enter_context(
                        InvertedIndexReader(index_id, self.postings_encoding, directory=self.output_dir)
                    )
                    for index_id in self.intermediate_indices
                ]
                self.merge(indices, merged_index)


if __name__ == "__main__":
    SPIMI_instance = SPIMIIndex(
        data_dir="collection",
        postings_encoding=VBEPostings,
        output_dir="spimi_index",
    )
    SPIMI_instance.index()
