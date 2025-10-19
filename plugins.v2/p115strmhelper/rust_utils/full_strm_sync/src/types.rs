use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::Deserialize;
use std::collections::HashSet;

#[derive(Deserialize, Debug, Clone)]
pub struct Config {
    pub pan_transfer_enabled: bool,
    pub pan_transfer_paths: Vec<String>,
    pub auto_download_mediainfo: bool,
    pub rmt_mediaext_set: HashSet<String>,
    pub download_mediaext_set: HashSet<String>,
    pub strm_generate_blacklist: Vec<String>,
    pub mediainfo_download_whitelist: Vec<String>,
    pub mediainfo_download_blacklist: Vec<String>,
    pub full_sync_min_file_size: u64,
    pub pan_media_dir: String,
}

#[derive(Clone, Debug)]
pub struct FileInput {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size: Option<u64>,
    pub pickcode: Option<String>,
    pub sha1: Option<String>,
}

impl<'source> FromPyObject<'source> for FileInput {
    fn extract(ob: &'source PyAny) -> PyResult<Self> {
        let dict: &'source PyDict = ob.downcast()?;

        let name: String = dict
            .get_item("name")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("Missing 'name' key"))?
            .extract()?;

        let path: String = dict
            .get_item("path")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("Missing 'path' key"))?
            .extract()?;

        let is_dir: bool = dict
            .get_item("is_dir")?
            .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyKeyError, _>("Missing 'is_dir' key"))?
            .extract()?;

        let size: Option<u64> = dict.get_item("size")?.and_then(|item| item.extract().ok());
        let pickcode: Option<String> = dict.get_item("pickcode")?.and_then(|item| item.extract().ok());
        let sha1: Option<String> = dict.get_item("sha1")?.and_then(|item| item.extract().ok());

        Ok(FileInput {
            name,
            path,
            is_dir,
            size,
            pickcode,
            sha1,
        })
    }
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct StrmInfo {
    pub pickcode: String,
    pub original_file_name: String,
    pub path_in_pan: String,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct DownloadInfo {
    pub pickcode: String,
    pub sha1: String,
    pub path_in_pan: String,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct SkipInfo {
    pub path_in_pan: String,
    pub reason: String,
}

#[pyclass(get_all, frozen)]
#[derive(Clone, Debug)]
pub struct FailInfo {
    pub path_in_pan: String,
    pub reason: String,
}

#[derive(Clone, Debug)]
pub enum ProcessingResult {
    Strm(StrmInfo),
    Download(DownloadInfo),
    Skip(SkipInfo),
    Fail(FailInfo),
}

#[pyclass(get_all)]
pub struct PackedResult {
    pub strm_results: Vec<StrmInfo>,
    pub download_results: Vec<DownloadInfo>,
    pub skip_results: Vec<SkipInfo>,
    pub fail_results: Vec<FailInfo>,
}
