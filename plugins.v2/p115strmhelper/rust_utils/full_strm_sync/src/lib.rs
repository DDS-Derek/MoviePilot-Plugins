mod processor;
mod types;

use processor::Processor;
use pyo3::prelude::*;
use types::*;

#[pyclass(name = "Processor")]
struct PyProcessor {
    processor: Processor,
}

#[pymethods]
impl PyProcessor {
    #[new]
    fn new(config_json: String) -> PyResult<Self> {
        let config: Config = serde_json::from_str(&config_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("解析 JSON 失败: {}", e)))?;
        let processor = Processor::new(config);
        Ok(PyProcessor { processor })
    }

    fn process_batch(&self, py: Python, batch: Vec<FileInput>) -> PyResult<PackedResult> {
        py.allow_threads(|| {
            Ok(self.processor.process_batch_rust(batch))
        })
    }
}

#[pymodule]
fn full_strm_sync(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyProcessor>()?;
    m.add_class::<StrmInfo>()?;
    m.add_class::<DownloadInfo>()?;
    m.add_class::<SkipInfo>()?;
    m.add_class::<FailInfo>()?;
    m.add_class::<PackedResult>()?;
    Ok(())
}
