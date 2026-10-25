此目录是可搬迁的离线测试夹具，媒体 `media/clip.bin` 为自制文本字节，非真实视频或 AI 产物。

`valid.json` 是路径相对本目录的模板。调用校验器前须将 `inputs.approved_media_roots` 和 `clips[].source_path` 绑定到夹具目录的绝对路径；可参照 `tests/contracts/test_resolve_blueprint_contract.py::load_fixture`。请勿相对当前工作目录解析。

生产 `validate_blueprint` 与 CLI 仍严格要求已批准的绝对路径，不因本夹具接受相对路径。搬迁不更改媒体内容或 SHA-256，不关闭媒体、symlink、许可验证，不扩大批准根。
