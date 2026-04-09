"""
PLFS Data Finder & Loader - Smart Version
==========================================

Handles your exact folder structure and guides you if data files are missing.

Author: PLFS Research Team
Version: 3.0.0
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import pandas as pd
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('PLFS_Finder')


class PLFSDataFinder:
    """
    Intelligently finds and loads PLFS data from your exact folder structure.
    """
    
    def __init__(self, root_path: str):
        """
        Initialize finder with root path.
        
        Args:
            root_path: Path to "Periodic Labour Force Survey" folder
        """
        self.root_path = Path(root_path)
        self.discovered_files = {
            'data_layout': [],
            'district_codes': [],
            'state_codes': [],
            'readme': [],
            'instructions': [],
            'household_data': [],
            'person_data': []
        }
    
    def scan_all(self) -> Dict[str, List[Path]]:
        """
        Scan all folders and categorize files.
        
        Returns:
            Dictionary of discovered files by category
        """
        logger.info("="*80)
        logger.info("SCANNING YOUR PLFS FOLDER STRUCTURE")
        logger.info("="*80)
        logger.info(f"\nRoot path: {self.root_path}\n")
        
        if not self.root_path.exists():
            raise FileNotFoundError(
                f"Folder not found: {self.root_path}\n"
                f"Please update the ROOT_PATH variable in the script."
            )
        
        # Scan all subfolders
        for folder in sorted(self.root_path.iterdir()):
            if folder.is_dir():
                self._scan_folder(folder)
        
        # Print summary
        self._print_summary()
        
        return self.discovered_files
    
    def _scan_folder(self, folder: Path):
        """Scan individual folder for files."""
        logger.info(f"📁 {folder.name}")
        
        file_count = 0
        for file_path in folder.glob("*"):
            if file_path.is_file():
                self._categorize_file(file_path)
                file_count += 1
        
        if file_count == 0:
            logger.info(f"   (empty)")
    
    def _categorize_file(self, file_path: Path):
        """Categorize file based on naming patterns."""
        filename = file_path.name.lower()
        
        # Data layout files
        if 'data_layout' in filename or 'datalayout' in filename:
            self.discovered_files['data_layout'].append(file_path)
            logger.info(f"   ✓ Data Layout: {file_path.name}")
        
        # District codes
        elif 'district' in filename and 'code' in filename:
            self.discovered_files['district_codes'].append(file_path)
            logger.info(f"   ✓ District Codes: {file_path.name}")
        
        # State codes  
        elif 'state' in filename and 'code' in filename:
            self.discovered_files['state_codes'].append(file_path)
            logger.info(f"   ✓ State Codes: {file_path.name}")
        
        # README files
        elif 'readme' in filename:
            self.discovered_files['readme'].append(file_path)
            logger.info(f"   ✓ README: {file_path.name}")
        
        # Instruction manuals
        elif 'instruction' in filename or 'manual' in filename:
            self.discovered_files['instructions'].append(file_path)
            logger.info(f"   ✓ Instructions: {file_path.name}")
        
        # Household data files (CSV/TXT)
        elif any(x in filename for x in ['hhv1', 'chhv1', 'household']):
            if file_path.suffix.lower() in ['.csv', '.txt']:
                self.discovered_files['household_data'].append(file_path)
                logger.info(f"   ✓ HOUSEHOLD DATA: {file_path.name}")
        
        # Person data files (CSV/TXT)
        elif any(x in filename for x in ['perv1', 'cperv1', 'person']):
            if file_path.suffix.lower() in ['.csv', '.txt']:
                self.discovered_files['person_data'].append(file_path)
                logger.info(f"   ✓ PERSON DATA: {file_path.name}")
    
    def _print_summary(self):
        """Print comprehensive summary."""
        logger.info("\n" + "="*80)
        logger.info("DISCOVERY SUMMARY")
        logger.info("="*80)
        
        # Reference files (always available)
        logger.info("\n📚 REFERENCE FILES FOUND:")
        logger.info(f"   Data Layouts: {len(self.discovered_files['data_layout'])} files")
        logger.info(f"   District Codes: {len(self.discovered_files['district_codes'])} files")
        logger.info(f"   State Codes: {len(self.discovered_files['state_codes'])} files")
        logger.info(f"   README files: {len(self.discovered_files['readme'])} files")
        logger.info(f"   Instructions: {len(self.discovered_files['instructions'])} files")
        
        # Data files (critical!)
        logger.info("\n📊 ACTUAL DATA FILES:")
        household_count = len(self.discovered_files['household_data'])
        person_count = len(self.discovered_files['person_data'])
        
        if household_count > 0:
            logger.info(f"   ✅ Household data: {household_count} files")
        else:
            logger.warning("   ❌ Household data: NOT FOUND")
        
        if person_count > 0:
            logger.info(f"   ✅ Person data: {person_count} files")
        else:
            logger.warning("   ❌ Person data: NOT FOUND")
        
        # Check if we have actual data
        if household_count == 0 and person_count == 0:
            logger.info("\n" + "="*80)
            logger.warning("⚠️  NO DATA FILES FOUND!")
            logger.info("="*80)
            self._print_data_help()
    
    def _print_data_help(self):
        """Print help on getting actual data files."""
        logger.info("""
🔍 WHAT YOU HAVE:
   - Data layout files (Excel) ✓
   - District codes ✓
   - State codes ✓
   - Documentation (README, Instructions) ✓

❌ WHAT'S MISSING:
   - Actual household data files (HHV1.csv or HHV1.txt)
   - Actual person data files (PerV1.csv or PerV1.txt)

📥 HOW TO GET THE DATA:

Option 1: Download from NSO Website
   1. Visit: http://microdata.gov.in/nada43/index.php/catalog/PLFS
   2. Register for an account (free)
   3. Request access to PLFS unit-level data
   4. Download the data files (CSV or TXT format)
   5. Place them in any year folder (e.g., July 2023-June 2024/)

Option 2: Use Sample/Demo Data
   If you just want to test the pipeline:
   1. I can create sample data files for testing
   2. Run the demo mode to see how everything works

Option 3: Request from Professor/Department
   Your university may already have access to the data
   Check with your supervisor or department library

📁 EXPECTED FILE NAMES:
   - HHV1.csv or HHV1.txt (Household data)
   - PerV1.csv or PerV1.txt (Person data)
   
   OR:
   
   - chhv1.csv (Household data)
   - cperv1.csv (Person data)

Once you have the data files, place them in:
   {}/July 2023-June 2024/

Then re-run this script!
""".format(self.root_path))
    
    def load_reference_files(self) -> Dict[str, pd.DataFrame]:
        """
        Load available reference files (state codes, district codes, etc.)
        
        Returns:
            Dictionary of DataFrames
        """
        logger.info("\n" + "="*80)
        logger.info("LOADING REFERENCE FILES")
        logger.info("="*80)
        
        reference_data = {}
        
        # Load state codes
        if self.discovered_files['state_codes']:
            latest_state = self.discovered_files['state_codes'][0]
            logger.info(f"\nLoading: {latest_state.name}")
            try:
                reference_data['states'] = pd.read_excel(latest_state)
                logger.info(f"  ✓ Loaded {len(reference_data['states'])} states")
            except Exception as e:
                logger.error(f"  ✗ Error: {str(e)}")
        
        # Load district codes (use most recent)
        if self.discovered_files['district_codes']:
            latest_district = max(
                self.discovered_files['district_codes'],
                key=lambda p: p.stat().st_mtime
            )
            logger.info(f"\nLoading: {latest_district.name}")
            try:
                reference_data['districts'] = pd.read_excel(latest_district)
                logger.info(f"  ✓ Loaded {len(reference_data['districts'])} districts")
            except Exception as e:
                logger.error(f"  ✗ Error: {str(e)}")
        
        # Load data layout (to understand structure)
        if self.discovered_files['data_layout']:
            latest_layout = max(
                self.discovered_files['data_layout'],
                key=lambda p: p.stat().st_mtime
            )
            logger.info(f"\nLoading: {latest_layout.name}")
            try:
                reference_data['data_layout'] = pd.read_excel(latest_layout)
                logger.info(f"  ✓ Loaded data layout with {len(reference_data['data_layout'])} rows")
            except Exception as e:
                logger.error(f"  ✗ Error: {str(e)}")
        
        return reference_data
    
    def create_sample_data(self, output_folder: Path, num_records: int = 1000):
        """
        Create sample/demo data for testing the pipeline.
        
        Args:
            output_folder: Where to save sample data
            num_records: Number of sample records to create
        """
        logger.info("\n" + "="*80)
        logger.info("CREATING SAMPLE DATA FOR TESTING")
        logger.info("="*80)
        
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Create sample household data
        logger.info(f"\nCreating {num_records} sample household records...")
        
        household_df = pd.DataFrame({
            'ST': np.random.randint(1, 36, num_records),
            'DC': np.random.randint(1, 800, num_records),
            'QTR': np.random.randint(1, 5, num_records),
            'VISIT': np.ones(num_records, dtype=int),
            'MFSU': np.random.randint(1, 99999, num_records),
            'SEG': np.random.randint(1, 3, num_records),
            'SSU': np.random.randint(1, 10, num_records),
            'YEAR': np.full(num_records, 2023),
            'SECTOR': np.random.choice([1, 2], num_records),
            'HH_SIZE': np.random.randint(1, 10, num_records),
            'MLTS': np.random.randint(100000, 2000000, num_records)  # Multiplier
        })
        
        # Create HHID
        household_df['HHID'] = (
            household_df['ST'].astype(str).str.zfill(2) +
            household_df['DC'].astype(str).str.zfill(3) +
            household_df['QTR'].astype(str) +
            household_df['VISIT'].astype(str) +
            household_df['MFSU'].astype(str).str.zfill(5) +
            household_df['SEG'].astype(str) +
            household_df['SSU'].astype(str).str.zfill(2) +
            household_df['YEAR'].astype(str)
        )
        
        # Save household data
        household_file = output_folder / "sample_household_data.csv"
        household_df.to_csv(household_file, index=False)
        logger.info(f"  ✓ Saved: {household_file}")
        
        # Create sample person data
        logger.info(f"\nCreating sample person records...")
        
        # Each household has 1-8 persons
        person_records = []
        for idx, row in household_df.iterrows():
            hh_size = row['HH_SIZE']
            for person_no in range(1, hh_size + 1):
                person_records.append({
                    'HHID': row['HHID'],
                    'PERSON_NO': person_no,
                    'AGE': np.random.randint(0, 85),
                    'SEX': np.random.choice([1, 2]),
                    'SECTOR': row['SECTOR'],
                    'Principal_Status': np.random.choice([11, 12, 21, 31, 41, 51, 81, 91, 92], p=[0.15, 0.05, 0.10, 0.20, 0.05, 0.15, 0.07, 0.15, 0.08]),
                    'MLTS': row['MLTS']
                })
        
        person_df = pd.DataFrame(person_records)
        
        # Save person data
        person_file = output_folder / "sample_person_data.csv"
        person_df.to_csv(person_file, index=False)
        logger.info(f"  ✓ Saved: {person_file}")
        
        logger.info(f"\n✅ Sample data created successfully!")
        logger.info(f"   Household records: {len(household_df):,}")
        logger.info(f"   Person records: {len(person_df):,}")
        logger.info(f"   Location: {output_folder}")
        
        return household_df, person_df


def main():
    """
    Main execution function.
    """
    
    print("\n" + "="*80)
    print(" PLFS DATA FINDER - Smart Version")
    print("="*80)
    
    # ========================================================================
    # CONFIGURE YOUR PATH HERE
    # ========================================================================
    
    # Option 1: Default bundle under project data/
    ROOT_PATH = Path("data/Periodic Labour Force Survey -20260408T175758Z-3-001/Periodic Labour Force Survey")

    # Option 2: Manual path (uncomment and edit if needed)
    # ROOT_PATH = Path("C:/Users/YourName/Downloads/Periodic Labour Force Survey -20260408T175758Z-3-001/Periodic Labour Force Survey")
    
    print(f"\n📂 Root path: {ROOT_PATH}\n")
    
    # ========================================================================
    # SCAN FOLDERS
    # ========================================================================
    
    finder = PLFSDataFinder(str(ROOT_PATH))
    discovered = finder.scan_all()
    
    # ========================================================================
    # LOAD AVAILABLE FILES
    # ========================================================================
    
    reference_data = finder.load_reference_files()
    
    # Print what we loaded
    if reference_data:
        logger.info("\n" + "="*80)
        logger.info("SUCCESSFULLY LOADED REFERENCE DATA")
        logger.info("="*80)
        
        for name, df in reference_data.items():
            logger.info(f"\n{name.upper()}:")
            logger.info(f"  Rows: {len(df):,}")
            logger.info(f"  Columns: {list(df.columns[:5])}...")
    
    # ========================================================================
    # CHECK FOR ACTUAL DATA
    # ========================================================================
    
    if not discovered['household_data'] and not discovered['person_data']:
        logger.info("\n" + "="*80)
        logger.info("NEXT STEPS")
        logger.info("="*80)
        
        response = input("\nWould you like to create SAMPLE DATA for testing? (y/n): ")
        
        if response.lower() == 'y':
            output_folder = ROOT_PATH / "sample_data"
            hh_df, per_df = finder.create_sample_data(output_folder, num_records=5000)
            
            logger.info("\n" + "="*80)
            logger.info("🎉 SUCCESS!")
            logger.info("="*80)
            logger.info(f"\nSample data created in: {output_folder}")
            logger.info("\nYou can now:")
            logger.info("  1. Test the full pipeline with this sample data")
            logger.info("  2. See how everything works")
            logger.info("  3. Build your website using the sample")
            logger.info("\nWhen you get real data, just replace the sample files!")
            
        else:
            logger.info("\n📥 To proceed with real analysis:")
            logger.info("  1. Download actual PLFS data from NSO")
            logger.info("  2. Place CSV/TXT files in any year folder")
            logger.info("  3. Re-run this script")
    
    else:
        logger.info("\n✅ Great! You have actual data files.")
        logger.info("   You can now run the complete pipeline.")
    
    logger.info("\n" + "="*80)
    logger.info("SCAN COMPLETE")
    logger.info("="*80)


if __name__ == "__main__":
    import numpy as np  # For sample data creation
    main()
