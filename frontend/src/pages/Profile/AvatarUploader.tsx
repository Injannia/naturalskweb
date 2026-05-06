import { useCallback, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import Cropper from 'react-easy-crop'
import type { Area } from 'react-easy-crop'
import axios from 'axios'
import { toast } from 'react-toastify'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import { useAuth } from '../../stores/authStore'
import type { AvatarUploadResponse, User } from '../../types'
import styles from './Profile.module.css'

async function getCroppedBlob(imageSrc: string, area: Area): Promise<Blob> {
  const image = new Image()
  image.src = imageSrc
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve()
    image.onerror = () => reject(new Error('image load'))
  })
  const canvas = document.createElement('canvas')
  canvas.width = area.width
  canvas.height = area.height
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(
    image,
    area.x,
    area.y,
    area.width,
    area.height,
    0,
    0,
    area.width,
    area.height,
  )
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('blob'))),
      'image/jpeg',
      0.92,
    )
  })
}

function errorMessage(e: unknown, fallback: string): string {
  if (axios.isAxiosError(e) && typeof e.response?.data?.detail === 'string') {
    return e.response.data.detail
  }
  return fallback
}

export default function AvatarUploader() {
  const { user, setUser } = useAuth()
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [imageSrc, setImageSrc] = useState<string | null>(null)
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [areaPx, setAreaPx] = useState<Area | null>(null)
  const [busy, setBusy] = useState(false)

  if (!user) return null
  const hasAvatar = (user.avatar_version ?? 0) > 0

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setImageSrc(reader.result as string)
      setCrop({ x: 0, y: 0 })
      setZoom(1)
    }
    reader.readAsDataURL(file)
    e.target.value = ''
  }

  const onCropComplete = useCallback((_: Area, pixels: Area) => setAreaPx(pixels), [])

  const save = async () => {
    if (!imageSrc || !areaPx) return
    setBusy(true)
    try {
      const blob = await getCroppedBlob(imageSrc, areaPx)
      const fd = new FormData()
      fd.append('file', blob, 'avatar.jpg')
      await api.post<AvatarUploadResponse>('/me/avatar', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const fresh = await api.get<User>('/auth/me')
      setUser(fresh.data)
      setImageSrc(null)
      toast.success('Аватар обновлён')
    } catch (e) {
      toast.error(errorMessage(e, 'Не удалось сохранить'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    try {
      await api.delete('/me/avatar')
      const fresh = await api.get<User>('/auth/me')
      setUser(fresh.data)
      toast.success('Аватар удалён')
    } catch (e) {
      toast.error(errorMessage(e, 'Ошибка'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.avatarUploader}>
      <AvatarImage userId={user.id} version={user.avatar_version ?? 0} size={128} />
      <div className={styles.avatarActions}>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={onPick}
        />
        <button
          className={styles.btnSecondary}
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          Загрузить
        </button>
        {hasAvatar && (
          <button className={styles.btnDanger} onClick={remove} disabled={busy}>
            Удалить
          </button>
        )}
      </div>

      {imageSrc && (
        <div
          className={styles.modalOverlay}
          onClick={() => !busy && setImageSrc(null)}
        >
          <div
            className={styles.modal}
            onClick={(e) => e.stopPropagation()}
            style={{ width: 'min(90vw, 480px)' }}
          >
            <h3>Обрезать аватар</h3>
            <div className={styles.cropArea}>
              <Cropper
                image={imageSrc}
                crop={crop}
                zoom={zoom}
                aspect={1}
                cropShape="round"
                showGrid={false}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            </div>
            <input
              type="range"
              min={1}
              max={3}
              step={0.05}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
              disabled={busy}
            />
            <div className={styles.modalActions}>
              <button
                className={styles.btnSecondary}
                onClick={() => setImageSrc(null)}
                disabled={busy}
              >
                Отмена
              </button>
              <button
                className={styles.btnPrimary}
                onClick={save}
                disabled={busy || !areaPx}
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
