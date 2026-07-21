"""
visuals.py
Multi-shot visual fetcher (Pixabay-ready)
"""
import os,re,requests
PIXABAY_SEARCH_URL="https://pixabay.com/api/videos/"
_used_urls=set()
def _clean(text):
    text=re.sub(r"[^a-zA-Z0-9\s]"," ",text.lower())
    return " ".join([w for w in text.split() if len(w)>2])
def _score(hit):
    s=0
    v=hit.get("videos",{})
    if "large" in v:s+=40
    elif "medium" in v:s+=30
    elif "small" in v:s+=20
    s+=min(hit.get("views",0)/1000,30)
    s+=min(hit.get("downloads",0)/1000,30)
    return s
def _search(query):
    r=requests.get(PIXABAY_SEARCH_URL,params={"key":os.environ["PIXABAY_API_KEY"],"q":_clean(query),"video_type":"film","per_page":15},timeout=30)
    if r.status_code!=200:return None
    hits=r.json().get("hits",[])
    hits.sort(key=_score,reverse=True)
    for hit in hits:
        vids=hit.get("videos",{})
        for tier in ("large","medium","small","tiny"):
            if tier in vids:
                url=vids[tier]["url"]
                if url in _used_urls:continue
                _used_urls.add(url)
                return url
    return None
def _download(url,path):
    r=requests.get(url,stream=True,timeout=60);r.raise_for_status()
    with open(path,"wb") as f:
        for c in r.iter_content(1024*1024):
            if c:f.write(c)
def fetch_visuals_for_script(script,config,workdir):
    os.makedirs(workdir,exist_ok=True)
    paths=[];clip_no=1
    for scene in script["scene_plan"]:
        scene_paths=[]
        for shot in scene.get("shots",[]):
            url=_search(shot["search"])
            if not url:continue
            out=os.path.join(workdir,f"clip_{clip_no}.mp4")
            _download(url,out)
            scene_paths.append(out);clip_no+=1
        if scene_paths:paths.append(scene_paths)
        else:paths.append(None)
    return paths
