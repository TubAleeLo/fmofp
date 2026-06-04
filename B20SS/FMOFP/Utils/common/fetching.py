import os
import sys

def fetch():
    # Determine project root dynamically
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    sys.path.insert(0, project_root)
    fmofp_path = os.path.join(project_root, 'FMOFP')
    sys.path.insert(0, fmofp_path)

def fetch_project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

def fetch_fmofp_path():
    return os.path.join(fetch_project_root(), 'FMOFP')

# Add project paths immediately when this module is imported
fetch()



# For debugging purposes
if __name__ == "__main__":
    print(f"Project root: {fetch_project_root()}")
    print(f"FMOFP path: {fetch_fmofp_path()}")