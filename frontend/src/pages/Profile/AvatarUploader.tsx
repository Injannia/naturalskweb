import { useCallback, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { ChangeEvent } from 'react'
import Cropper from 'react-easy-crop'
import type { Area } from 'react-easy-crop'
import { extractApiError as errorMessage } from '../../utils/apiError'
import { toast } from 'react-toastify'
import api from '../../api/client'
import AvatarImage from '../../components/AvatarImage'
import { useAuth } from '../../stores/authStore'
import { Button } from '../../components/ui'
import type { AvatarUploadResponse } from '../../types'
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
      const { data } = await api.post<AvatarUploadResponse>('/me/avatar', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUser({ ...user, avatar_version: data.avatar_version })
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
      setUser({ ...user, avatar_version: (user.avatar_version ?? 0) + 1 })
      toast.success('Аватар удалён')
    } catch (e) {
      toast.error(errorMessage(e, 'Ошибка'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className={styles.avatarRing}>
        <AvatarImage userId={user.id} version={user.avatar_version ?? 0} size={160} />
      </div>
      <div className={styles.avatarActions}>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={onPick}
        />
        <Button
          variant="primary"
          size="sm"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          Загрузить
        </Button>
        {hasAvatar && (
          <Button variant="dangerOutline" size="sm" onClick={remove} disabled={busy}>
            Удалить
          </Button>
        )}
      </div>

      {imageSrc && createPortal(
        <div
          className={styles.modalOverlay}
          onClick={() => !busy && setImageSrc(null)}
        >
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
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
              <Button variant="ghost" onClick={() => setImageSrc(null)} disabled={busy}>
                Отмена
              </Button>
              <Button variant="primary" onClick={save} disabled={busy || !areaPx} loading={busy}>
                Сохранить
              </Button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}
