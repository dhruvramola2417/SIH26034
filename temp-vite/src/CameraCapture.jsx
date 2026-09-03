import { useEffect, useRef, useState } from "react";

export default function CameraCapture({
  onCaptured,
  onClose,
  packageSide,
  scanSessionId
}) {

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const [error, setError] = useState("");
  const [starting, setStarting] = useState(true);

  useEffect(() => {
    startCamera();

    return () => {
      stopCamera();
    };
  }, []);

  async function startCamera() {
    try {
      setStarting(true);
      setError("");

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" }
        },
        audio: false
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err) {
      console.error(err);
      setError(
        "Could not access the camera. Please allow camera permission and try again."
      );
    } finally {
      setStarting(false);
    }
  }

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }

  function capturePhoto() {
  const video = videoRef.current;
  const canvas = canvasRef.current;

  if (!video || !canvas) return;

  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;

  const context = canvas.getContext("2d");

  context.drawImage(
    video,
    0,
    0,
    canvas.width,
    canvas.height
  );

  canvas.toBlob((blob) => {
    if (!blob) return;

    const file = new File(
      [blob],
      `camera-${Date.now()}.jpg`,
      {
        type: "image/jpeg"
      }
    );

    // Metadata for this camera capture
    const metadata = {
      package_side: "back",
      scan_session_id: "session_123",
      capture_method: "live_camera",
      client_timestamp: new Date().toISOString(),
      device_orientation: "portrait"
      
    };

    // Send both the image and metadata to the parent component
    onCaptured(file, metadata);

    stopCamera();
    onClose();
  }, "image/jpeg", 0.9);
}

   

  function handleClose() {
    stopCamera();
    onClose();
  }

  return (
    <div className="camera-overlay">
      <div className="camera-modal">

        <div className="camera-header">
          <h2>Capture Product Image</h2>

          <button onClick={handleClose}>
            ✕
          </button>
        </div>

        {error ? (
          <div className="camera-error">
            <p>{error}</p>

            <button onClick={startCamera}>
              Try Again
            </button>
          </div>
        ) : (
          <>
            <div className="camera-preview">
              {starting && (
                <p>Starting camera...</p>
              )}

            <div className="camera-frame">
  <video
    ref={videoRef}
    autoPlay
    playsInline
    muted
    className="camera-preview"
  />

  <div className="label-guide">
    <span>Align the label inside this box</span>
  </div>
</div>

              <canvas
                ref={canvasRef}
                style={{ display: "none" }}
              />
            </div>

            <div className="camera-controls">
              <button
                onClick={capturePhoto}
                disabled={starting}
              >
                📸 Capture
              </button>

              <button onClick={handleClose}>
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}