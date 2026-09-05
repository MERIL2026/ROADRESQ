from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_client_ip,
    get_current_active_user,
    get_db_session,
    get_request_id,
    get_user_agent,
)
from app.models.user import User
from app.schemas.auth import (
    LogoutRequest,
    MessageResponse,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.common import APIResponse, ResponseMeta
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


@router.post(
    "/register",
    response_model=APIResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer or provider account",
)
async def register(
    data: UserRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[TokenResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AuthService(session)
    token_bundle = await service.register(
        data=data, ip_address=ip_address, user_agent=user_agent
    )
    await session.commit()

    return APIResponse(
        data=token_bundle,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Authenticate with phone or email credentials",
)
async def login(
    data: UserLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[TokenResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AuthService(session)
    token_bundle = await service.login(
        data=data, ip_address=ip_address, user_agent=user_agent
    )
    await session.commit()

    return APIResponse(
        data=token_bundle,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/refresh",
    response_model=APIResponse[TokenRefreshResponse],
    status_code=status.HTTP_200_OK,
    summary="Rotate and refresh JWT access credentials",
)
async def refresh_token(
    data: TokenRefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[TokenRefreshResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AuthService(session)
    refreshed_tokens = await service.refresh_tokens(
        data=data, ip_address=ip_address, user_agent=user_agent
    )
    await session.commit()

    return APIResponse(
        data=refreshed_tokens,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/logout",
    response_model=APIResponse[MessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Invalidate active session and refresh token",
)
async def logout(
    request: Request,
    data: LogoutRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[MessageResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AuthService(session)
    result = await service.logout(
        current_user=current_user,
        data=data,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await session.commit()

    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve profile of currently authenticated user",
)
async def get_current_user_profile(
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> APIResponse[UserResponse]:
    request_id = get_request_id(request)
    user_resp = UserResponse(
        id=current_user.id,
        role=current_user.role,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        email=current_user.email,
        status=current_user.status,
        last_login_at=current_user.last_login_at,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )
    return APIResponse(
        data=user_resp,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/otp/request",
    response_model=APIResponse[OTPRequestResponse],
    status_code=status.HTTP_200_OK,
    summary="Request a 6-digit OTP code for phone verification",
)
async def request_otp(
    data: OTPRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[OTPRequestResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AuthService(session)
    result = await service.request_otp(
        data=data, ip_address=ip_address, user_agent=user_agent
    )
    await session.commit()

    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )


@router.post(
    "/otp/verify",
    response_model=APIResponse[OTPVerifyResponse],
    status_code=status.HTTP_200_OK,
    summary="Verify received OTP code",
)
async def verify_otp(
    data: OTPVerifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[OTPVerifyResponse]:
    request_id = get_request_id(request)
    ip_address = get_client_ip(request)
    user_agent = get_user_agent(request)

    service = AuthService(session)
    result = await service.verify_otp(
        data=data, ip_address=ip_address, user_agent=user_agent
    )
    await session.commit()

    return APIResponse(
        data=result,
        meta=ResponseMeta(request_id=request_id),
    )
