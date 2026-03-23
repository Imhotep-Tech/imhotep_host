import os
import git
import tempfile
import shutil

def clone_public_repo(repo_url: str, branch: str = "main", target_dir: str = "/tmp/imhotep_builds/"):
    """Clones a public GitHub repository into a temporary directory."""
    os.makedirs(target_dir, exist_ok=True)
    
    #extract the repo name
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    
    #creates the folder with a unique name
    temp_dir = tempfile.mkdtemp(prefix=f"{repo_name}_", dir=target_dir)
    
    print(f"Cloning {repo_url} (Branch: {branch}) into {temp_dir}...")
    
    try:
        # Clone the specific branch of the repo into the unique folder
        git.Repo.clone_from(repo_url, temp_dir, branch=branch)
        print("Clone successful.")
        return temp_dir
        
    except git.exc.GitCommandError as e:
        # If the clone fails (bad URL, private repo, or wrong branch name)
        print(f"Git clone failed: {e}")
        
        # Immediately delete the empty folder so it doesn't take up disk space
        cleanup_build_dir(temp_dir)
        
        # Raise a clean error that FastAPI can eventually send back to the React UI
        raise ValueError(f"Failed to clone repository. Please verify the URL and ensure the '{branch}' branch exists.")

def cleanup_build_dir(temp_dir: str):
    """Deletes the source code completely to free up disk space."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary build directory: {temp_dir}")