from pathlib import Path
import shutil
import config as cfg
from utils import pdfs_to_markdowns, clear_directory_contents

class DocumentManager:

    def __init__(self, rag_system, source_collection=None):
        self.rag_system = rag_system
        # Si source_collection es normas → usar colección y directorio de normas
        self.is_normas = (source_collection == cfg.NORMAS_COLLECTION)
        self.markdown_dir = Path(cfg.NORMAS_MARKDOWN_DIR if self.is_normas else cfg.MARKDOWN_DIR)
        self.collection_name = source_collection or rag_system.collection_name
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir = Path(cfg.PDF_DIR)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        
    def add_documents(self, document_paths, metadata_urls=None, progress_callback=None):
        if not document_paths:
            return 0, 0, []
            
        import json
        if metadata_urls and isinstance(metadata_urls, str):
            try:
                metadata_urls = json.loads(metadata_urls)
            except Exception:
                metadata_urls = {}
        elif not isinstance(metadata_urls, dict):
            metadata_urls = {}
            
        document_paths = [document_paths] if isinstance(document_paths, str) else document_paths
        
        valid_extensions = [".pdf", ".md"]
        valid_paths = []
        rejected = []
        for p in document_paths:
            if p and Path(p).suffix.lower() in valid_extensions:
                valid_paths.append(p)
            elif p:
                rejected.append(Path(p).name)
        
        if rejected:
            print(f"⚠️ Archivos rechazados (extensión no soportada): {rejected}")
        
        document_paths = valid_paths
        if not document_paths:
            return 0, 0, rejected
            
        added = 0
        skipped = 0
            
        for i, doc_path in enumerate(document_paths):
            if progress_callback:
                progress_callback((i + 1) / len(document_paths), f"Processing {Path(doc_path).name}")
                
            doc_name = Path(doc_path).stem
            md_path = self.markdown_dir / f"{doc_name}.md"
            
            if md_path.exists():
                skipped += 1
                continue
                
            try:            
                if Path(doc_path).suffix.lower() == ".md":
                    shutil.copy(doc_path, md_path)
                else:
                    pdf_dest = self.pdf_dir / f"{doc_name}.pdf"
                    if not pdf_dest.exists():
                        shutil.copy(doc_path, pdf_dest)
                    pdfs_to_markdowns(str(doc_path), overwrite=False)            
                
                # Soporte para metadata enriquecida (dict) o legacy (string)
                file_meta = metadata_urls.get(f"{doc_name}.md") or metadata_urls.get(f"{doc_name}.pdf")
                if isinstance(file_meta, dict):
                    source_url = file_meta.pop("source_url", None)
                    extra_metadata = file_meta  # entidad_id, tipo_dispositivo, etc.
                else:
                    source_url = file_meta
                    extra_metadata = None
                parent_chunks, child_chunks = self.rag_system.chunker.create_chunks_single(
                    md_path, source_url, extra_metadata=extra_metadata
                )
                
                if not child_chunks:
                    skipped += 1
                    continue
                
                collection = self.rag_system.vector_db.get_collection(self.collection_name)
                collection.add_documents(child_chunks)
                self.rag_system.parent_store.save_many(parent_chunks)
                
                added += 1
                
            except Exception as e:
                print(f"Error processing {doc_path}: {e}")
                skipped += 1
            
        return added, skipped, rejected
    
    def get_markdown_files(self):
        if not self.markdown_dir.exists():
            return []
        return sorted([p.name.replace(".md", ".pdf") for p in self.markdown_dir.glob("*.md")])
    
    def clear_all(self):
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(self.markdown_dir)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(self.pdf_dir)
        
        self.rag_system.parent_store.clear_store()
        self.rag_system.vector_db.delete_collection(self.rag_system.collection_name)
        self.rag_system.vector_db.create_collection(self.rag_system.collection_name)
