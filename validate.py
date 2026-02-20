import pandas as pd

# File paths
BGD_lab_file = "data/lab/BGD_lab_results.csv"
BGD_metadata_file = "data/metadata/BGD_metadata.xlsx"

# Read files
BGD_lab_df = pd.read_csv(BGD_lab_file)
BGD_metadata_df = pd.read_excel(BGD_metadata_file)

print("Lab file shape:", BGD_lab_df.shape)
print("Metadata file shape:", BGD_metadata_df.shape)

print("\nLab columns:")
print(BGD_lab_df.columns)

print("\nMetadata columns:")
print(BGD_metadata_df.columns)