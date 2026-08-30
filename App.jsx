import { useRef, useState } from "react";
import "./App.css";
import CameraCapture from "./CameraCapture";


const API_URL = "http://127.0.0.1:8000";

export default function App() {
  const fileInputRef = useRef(null);
  
  
  const [cameraOpen, setCameraOpen] = useState(false);
  const [selectedSide, setSelectedSide] = useState("front");
  const [images, setImages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  function openCameraOrGallery() {
    fileInputRef.current?.click();
  }

  async function handleImageSelection(event) {
  const files = Array.from(event.target.files || []);
  const accepted = [];

  for (const file of files) {
    const quality = await checkImageQuality(file);

    if (!quality.passed) {
      setMessage(`${file.name}: ${quality.reason}`);
      continue;
    }

    accepted.push({
      id: crypto.randomUUID(),
      file,
      side: selectedSide,
      previewUrl: URL.createObjectURL(file),
      status: "ready",
      serverData: null
    });
  }

  setImages((current) => [...current, ...accepted]);
  event.target.value = "";
}
     
  function addCapturedFile(file,metadata) {
    
    const item = {
        id: crypto.randomUUID(),
        file,
        side: selectedSide,
        previewUrl: URL.createObjectURL(file),
        status: "ready",
        serverData: null,
        metadata
    };

    setImages(current => [...current, item]);
}


  function removeImage(id) {
    setImages((current) => {
      const target = current.find((item) => item.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return current.filter((item) => item.id !== id);
    });
  }

  async function uploadAllImages() {
    if (images.length === 0) {
      setMessage("Capture or upload at least one label image first.");
      return;
    }

    setUploading(true);
    setMessage("");

    try {
      const updated = [];

      for (const item of images) {
       const formData = new FormData();

formData.append("side", item.side);
formData.append(
  "capture_method",
  item.metadata?.capture_method || "live_camera"
);
formData.append(
  "client_timestamp",
  item.metadata?.client_timestamp || new Date().toISOString()
);
formData.append("image", item.file);

        const response = await fetch(`${API_URL}/api/v1/scans`, {
          method: "POST",
          body: formData
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || "Upload failed.");
        }

        updated.push({
          ...item,
          status: "uploaded",
          serverData: data
        });
      }

      setImages(updated);
      setMessage("Images uploaded successfully. Ready for compliance processing.");
    } catch (error) {
      setMessage(`Upload error: ${error.message}`);
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="page">
      <section className="card">
        <h1>LMPC Label Scanner</h1>
        <p className="subtitle">
          Capture clear photos of the package declarations for automated compliance screening.
        </p>

        <label className="field-label" htmlFor="side">
          Package side
        </label>

        <select
          id="side"
          value={selectedSide}
          onChange={(event) => setSelectedSide(event.target.value)}
        >
          <option value="front">Front</option>
          <option value="back">Back</option>
          <option value="left_side">Left side</option>
          <option value="right_side">Right side</option>
          <option value="top">Top</option>
          <option value="bottom">Bottom</option>
        </select>

        <input
          ref={fileInputRef}
          className="hidden-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          multiple
          onChange={handleImageSelection}
        />
<div className="button-row">
  <button className="primary-button" onClick={() => setCameraOpen(true)}>
    Open Live Camera
  </button>

  <button className="secondary-button" onClick={openCameraOrGallery}>
    Upload from Gallery
  </button>
</div>

        <p className="hint">
          On phones, this requests the rear camera where supported. On desktops, it opens the file picker.
        </p>

        {images.length > 0 && (
          <>
            <h2>Captured images</h2>

            <div className="image-grid">
              {images.map((item) => (
                <article className="image-card" key={item.id}>
                  <img src={item.previewUrl} alt={`${item.side} package`} />

                  <div className="image-meta">
                    <span>{item.side.replace("_", " ")}</span>
                    <small>{item.file.name}</small>
                    <small>Status: {item.status}</small>
                  </div>

                  <button
                    className="remove-button"
                    onClick={() => removeImage(item.id)}
                    disabled={uploading}
                  >
                    Remove
                  </button>
                </article>
              ))}
            </div>

            <button
              className="primary-button"
              onClick={uploadAllImages}
              disabled={uploading}
            >
              {uploading ? "Uploading..." : "Upload and Start Scan"}
            </button>
          </>
        )}

        {message && <p className="message">{message}</p>}
        {cameraOpen && (
  <CameraCapture
    onCaptured={addCapturedFile}
    onClose={() => setCameraOpen(false)}
     packageSide={selectedSide}
  scanSessionId="session_123"
  />
)}

      </section>
    </main>
  );
}
async function checkImageQuality(file) {
  const imageUrl = URL.createObjectURL(file);

  try {
    const image = await new Promise((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = reject;
      element.src = imageUrl;
    });

    const minimumWidth = 1280;
    const minimumHeight = 720;

    if (image.width < minimumWidth || image.height < minimumHeight) {
      return {
        passed: false,
        reason: "Image resolution is too low. Use a clearer, closer photo."
      };
    }

    return {
      passed: true,
      reason: "Basic quality check passed."
    };
  } finally {
    URL.revokeObjectURL(imageUrl);
  }
}