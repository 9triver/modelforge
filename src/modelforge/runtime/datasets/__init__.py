"""标准数据 loader。

- forecasting.load_forecasting_csv: CSV/Parquet -> DataFrame
- image_classification.iter_image_folder: ImageFolder -> Iterator[(Image, label)]
- image_classification.unpack_zip: 用户上传 ZIP 解压（防 zip-slip）

按 task 拆模块，避免 vision 没装 Pillow 时导入 forecasting 也炸。
"""
