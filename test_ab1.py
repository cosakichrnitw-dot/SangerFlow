from core.ab1_reader import read_ab1


result = read_ab1("C2_FishF1.ab1")

print("Sequence:")
print(result["sequence"])

print("\nLength:")
print(result["length"])

print("\nFirst 20 quality scores:")
print(result["quality"][:20])

print("\nChromatogram:")
print(result["traces"].keys())

print("\nTrace length:")
print(len(result["traces"]["A"]))