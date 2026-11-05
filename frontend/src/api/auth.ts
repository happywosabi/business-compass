/** 登录注册接口，对应后端 backend/app/auth/router.py */

import { api } from './client'
import type { components } from './schema'

type Schemas = components['schemas']
export type User = Schemas['UserOut']
type Message = Schemas['MessageOut']

export const authApi = {
  me: () => api.get<User>('/api/auth/me', { silent401: true }),

  login: (body: Schemas['LoginRequest']) =>
    api.post<User>('/api/auth/login', body, { silent401: true }),

  register: (body: Schemas['RegisterRequest']) => api.post<Message>('/api/auth/register', body),

  logout: () => api.post<Message>('/api/auth/logout'),

  verifyEmail: (token: string) => api.post<Message>('/api/auth/verify-email', { token }),

  resendVerification: () => api.post<Message>('/api/auth/resend-verification'),

  forgotPassword: (email: string) => api.post<Message>('/api/auth/forgot-password', { email }),

  resetPassword: (body: Schemas['ResetPasswordRequest']) =>
    api.post<Message>('/api/auth/reset-password', body),

  changePassword: (body: Schemas['ChangePasswordRequest']) =>
    api.post<Message>('/api/auth/change-password', body),
}
