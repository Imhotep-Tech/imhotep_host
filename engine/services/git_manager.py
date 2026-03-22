import os
import git
import tempfile
import shutil

def clone_public_repo(repo_url: str, target_dir: str = "/tmp/imhotep_builds/"):
    """Clones a public GitHub repository into a temporary directory."""
    os.makedirs(target_dir, exist_ok=True)
    
    #extract the repo name
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    
    #creates the folder with a unique name
    temp_dir = tempfile.mkdtemp(prefix=f"{repo_name}_", dir=target_dir)
    
    #clone the repo into that unique folder
    git.Repo.clone_from(repo_url, temp_dir)
    
    return temp_dir

def cleanup_build_dir(temp_dir: str):
    """Deletes the source code completely to free up disk space."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary build directory: {temp_dir}")