from bsbi import BSBIIndex
from compression import VBEPostings


BSBI_instance = BSBIIndex(data_dir = 'collection',
                          postings_encoding = VBEPostings,
                          output_dir = 'index')

prefixes = ["preg", "meta", "cryst", "psych"]
queries = ["lipid meta", "psychodr", "the cryst"]

print("Term Autocomplete")
for prefix in prefixes:
    print("Prefix :", prefix)
    print(BSBI_instance.autocomplete(prefix, k = 10))
    print()

print("Query Autocomplete")
for query in queries:
    print("Query  :", query)
    print(BSBI_instance.autocomplete_query(query, k = 10))
    print()
